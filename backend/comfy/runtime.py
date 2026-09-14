from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.comfy.client import ComfyClient, ComfyClientError, comfy_url_from_env
from backend.comfy.converter import WorkflowConversionError, ui_workflow_to_prompt
from backend.db import Database, ROOT
from backend.models import GenerationTaskCreate, WorkflowManifest

OUTPUT_ROOT = ROOT / 'storage' / 'outputs'
_RUNTIME_LOCK = threading.Lock()

_DURATION_SECOND_FIELDS = {
    'duration',
    'seconds',
    'duration_sec',
    'duration_secs',
    'duration_seconds',
}
_DURATION_FRAME_FIELDS = {
    'frames',
    'frame_count',
    'framecount',
    'total_frames',
    'totalframes',
    'num_frames',
    'numframes',
    'length',
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(db: Database, task_id: str, event: str, message: str = '', data: dict[str, Any] | None = None) -> None:
    with db.connect() as conn:
        conn.execute(
            'INSERT INTO generation_task_events(task_id,event,message,data_json,created_at) VALUES(?,?,?,?,?)',
            (task_id, event, message, json.dumps(data or {}, ensure_ascii=False), _now()),
        )


def _update_task(db: Database, task_id: str, **values: Any) -> None:
    if not values:
        return
    fields = ', '.join(f'{key}=?' for key in values)
    with db.connect() as conn:
        conn.execute(f'UPDATE generation_tasks SET {fields} WHERE id=?', (*values.values(), task_id))


def create_task(db: Database, payload: GenerationTaskCreate) -> str:
    task_id = f'task-{uuid.uuid4().hex[:12]}'
    with db.connect() as conn:
        row = conn.execute('SELECT id FROM workflows WHERE id=?', (payload.workflowId,)).fetchone()
        if row is None:
            raise ValueError('workflow_not_found')
        conn.execute(
            """
            INSERT INTO generation_tasks(
                id, workflow_id, client_app, project_id, episode_id, shot_id, status,
                inputs_json, parameters_json, progress, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                task_id,
                payload.workflowId,
                payload.clientApp,
                payload.projectId,
                payload.episodeId,
                payload.shotId,
                'WAITING',
                json.dumps(payload.inputs, ensure_ascii=False),
                json.dumps(payload.parameters, ensure_ascii=False),
                0,
                _now(),
            ),
        )
    _event(db, task_id, 'CREATED', '任务已创建')
    thread = threading.Thread(target=_run_task_guarded, args=(db, task_id), daemon=True, name=f'cws-{task_id}')
    thread.start()
    return task_id


def _run_task_guarded(db: Database, task_id: str) -> None:
    with _RUNTIME_LOCK:
        try:
            run_task(db, task_id)
        except WorkflowConversionError as exc:
            _update_task(db, task_id, status='NEEDS_REVIEW', error=str(exc), finished_at=_now())
            _event(db, task_id, 'NEEDS_REVIEW', str(exc))
        except ComfyClientError as exc:
            # A transport failure after submission may mean the task actually
            # reached ComfyUI. Mark UNKNOWN rather than retrying automatically.
            with db.connect() as conn:
                row = conn.execute('SELECT prompt_id,status FROM generation_tasks WHERE id=?', (task_id,)).fetchone()
            prompt_id = row['prompt_id'] if row else None
            status = 'UNKNOWN' if prompt_id else 'FAILED'
            _update_task(db, task_id, status=status, error=str(exc), finished_at=_now())
            _event(db, task_id, status, str(exc))
        except Exception as exc:  # noqa: BLE001 - task boundary must persist failures
            _update_task(db, task_id, status='FAILED', error=str(exc), finished_at=_now())
            _event(db, task_id, 'FAILED', str(exc))


def run_task(db: Database, task_id: str) -> None:
    with db.connect() as conn:
        task = conn.execute('SELECT * FROM generation_tasks WHERE id=?', (task_id,)).fetchone()
        if task is None:
            return
        workflow = conn.execute('SELECT * FROM workflows WHERE id=?', (task['workflow_id'],)).fetchone()
    if workflow is None:
        raise RuntimeError('workflow_not_found')

    _update_task(db, task_id, status='PREPARING', started_at=_now(), progress=0.05)
    _event(db, task_id, 'PREPARING', '准备 Runtime Workflow')

    manifest = WorkflowManifest.model_validate(json.loads(workflow['manifest_json']))
    workflow_path = Path(workflow['api_workflow_path'] or workflow['original_path'])
    if not workflow_path.is_file():
        raise RuntimeError(f'workflow_file_missing: {workflow_path}')
    source = json.loads(workflow_path.read_text(encoding='utf-8'))

    client = ComfyClient(comfy_url_from_env())
    if isinstance(source.get('nodes'), list):
        _event(db, task_id, 'CONVERTING', '将 UI Workflow 转换为 API Prompt')
        prompt = ui_workflow_to_prompt(source, client.object_info())
    else:
        prompt = json.loads(json.dumps(source))

    inputs = json.loads(task['inputs_json'] or '{}')
    parameters = json.loads(task['parameters_json'] or '{}')
    duration_plan = _apply_manifest_values(prompt, manifest, inputs, parameters, source, client)
    if duration_plan:
        _event(
            db,
            task_id,
            'DURATION_APPLIED',
            f"动态时长 {duration_plan['seconds']}s → {duration_plan['frames']} frames @ {duration_plan['fps']}fps",
            duration_plan,
        )

    runtime_dir = ROOT / 'storage' / 'runtime' / task_id
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_path = runtime_dir / 'prompt.json'
    runtime_path.write_text(json.dumps(prompt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    _update_task(db, task_id, runtime_workflow_path=str(runtime_path), status='SUBMITTING', progress=0.12)
    _event(db, task_id, 'SUBMITTING', '提交到 ComfyUI')

    response = client.submit_prompt(prompt)
    prompt_id = str(response.get('prompt_id') or '')
    if not prompt_id:
        node_errors = response.get('node_errors')
        raise WorkflowConversionError(f'ComfyUI rejected prompt: {node_errors or response}')

    _update_task(db, task_id, prompt_id=prompt_id, status='RUNNING', progress=0.2)
    _event(db, task_id, 'QUEUED', f'Prompt ID: {prompt_id}', {'promptId': prompt_id})

    history = client.wait_for_history(prompt_id, timeout=manifest.runtime.outputTimeout)
    status_info = history.get('status') or {}
    if status_info.get('status_str') == 'error':
        messages = status_info.get('messages') or []
        raise RuntimeError(f'ComfyUI execution error: {messages}')

    _update_task(db, task_id, progress=0.92)
    saved = _collect_outputs(db, task_id, workflow['id'], history, client)
    _update_task(db, task_id, status='SUCCEEDED', progress=1.0, finished_at=_now(), error=None)
    _event(db, task_id, 'SUCCEEDED', f'生成完成，共保存 {len(saved)} 个输出', {'outputs': saved})


def _resolve_prompt_field(node_inputs: dict[str, Any], requested: str | None) -> str | None:
    if requested and requested in node_inputs:
        return requested
    aliases = {
        'text': ('text', 'text_in', 'prompt'),
        'image': ('image', 'image_path', 'filename'),
        'duration': ('duration', 'seconds', 'frames', 'length', 'frame_count', 'total_frames'),
        'fps': ('fps', 'frame_rate', 'framerate'),
    }
    for candidate in aliases.get(requested or '', (requested,) if requested else ()):
        if candidate and candidate in node_inputs:
            return candidate
    return requested


def _upload_if_path(value: Any, client: ComfyClient) -> Any:
    if not isinstance(value, str):
        return value
    path = Path(value)
    if not path.is_file():
        return value
    result = client.upload_image(path)
    return result.get('name') or path.name


def _iter_duration_states(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {'durationState', 'duration_state'} and isinstance(item, dict):
                yield item
            yield from _iter_duration_states(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_duration_states(item)


def _duration_plan(seconds: float, source: dict[str, Any], fps_override: float | None = None) -> dict[str, Any]:
    seconds = float(seconds)
    if seconds <= 0:
        raise WorkflowConversionError('duration must be greater than 0')

    fps = float(fps_override) if fps_override and float(fps_override) > 0 else 24.0
    padding = 4.0
    state_source = None
    for state in _iter_duration_states(source):
        state_fps = state.get('fps')
        state_step = state.get('step')
        state_plus = state.get('plus')
        if not fps_override:
            if isinstance(state_fps, (int, float)) and state_fps > 0:
                fps = float(state_fps)
            elif isinstance(state_step, (int, float)) and state_step > 0:
                fps = float(state_step)
        recipe_name = str(state.get('recipeName') or state.get('recipe_name') or '').strip().lower()
        if recipe_name == 'minimax h3':
            padding = 4.0
        elif isinstance(state_plus, (int, float)):
            padding = float(state_plus)
        state_source = 'durationState'
        break

    frames = max(1, round(seconds * fps + padding))
    return {
        'seconds': seconds,
        'fps': int(fps) if fps.is_integer() else fps,
        'padding': int(padding) if padding.is_integer() else padding,
        'frames': frames,
        'source': state_source or 'fallback-24fps-plus4',
        'updated': [],
    }


def _duration_to_frames(seconds: float, source: dict[str, Any], node_id: str | None = None, fps: float | None = None) -> int:
    # node_id is kept for backward compatibility with older manifests. The
    # source-level duration state is more reliable because some workflows keep
    # the duration metadata on a UI helper node while frame fields live on
    # downstream generation nodes.
    del node_id
    return int(_duration_plan(seconds, source, fps)['frames'])


def _apply_dynamic_duration(
    prompt: dict[str, Any],
    source: dict[str, Any],
    seconds: float,
    fps: float | None = None,
) -> dict[str, Any]:
    plan = _duration_plan(seconds, source, fps)
    frames = int(plan['frames'])
    updated: list[str] = []

    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        node_inputs = node.get('inputs')
        if not isinstance(node_inputs, dict):
            continue
        for field, current in list(node_inputs.items()):
            normalized = str(field).strip().lower().replace('-', '_')
            if normalized in _DURATION_FRAME_FIELDS and not isinstance(current, bool):
                node_inputs[field] = frames
                updated.append(f'{node_id}.{field}=frames')
            elif normalized in _DURATION_SECOND_FIELDS and isinstance(current, (int, float)) and not isinstance(current, bool):
                node_inputs[field] = float(seconds)
                updated.append(f'{node_id}.{field}=seconds')

    plan['updated'] = updated
    return plan


def _apply_manifest_values(
    prompt: dict[str, Any],
    manifest: WorkflowManifest,
    values: dict[str, Any],
    parameters: dict[str, Any],
    source: dict[str, Any],
    client: ComfyClient,
) -> dict[str, Any] | None:
    for item in manifest.inputs:
        if item.key not in values or not item.mapping.nodeId:
            continue
        node = prompt.get(str(item.mapping.nodeId))
        if not isinstance(node, dict):
            continue
        node_inputs = node.setdefault('inputs', {})
        field = _resolve_prompt_field(node_inputs, item.mapping.field)
        if not field:
            continue
        value = values[item.key]
        if item.type == 'image':
            value = _upload_if_path(value, client)
        node_inputs[field] = value

    fps_value: float | None = None
    for key, value in parameters.items():
        if str(key).lower() in {'fps', 'frame_rate', 'framerate'}:
            try:
                fps_value = float(value)
            except (TypeError, ValueError):
                fps_value = None
            break

    duration_seconds: float | None = None
    for item in manifest.parameters:
        if item.key not in parameters:
            continue
        value = parameters[item.key]
        is_duration = item.mapping.strategy == 'duration-to-frames' or item.key.lower() in {
            'duration', 'seconds', 'duration_seconds', 'video_duration'
        }
        if is_duration:
            try:
                duration_seconds = float(value)
            except (TypeError, ValueError) as exc:
                raise WorkflowConversionError(f'invalid duration: {value!r}') from exc

        if not item.mapping.nodeId:
            continue
        node = prompt.get(str(item.mapping.nodeId))
        if not isinstance(node, dict):
            continue
        node_inputs = node.setdefault('inputs', {})
        field = _resolve_prompt_field(node_inputs, item.mapping.field)
        if item.mapping.strategy == 'duration-to-frames' and duration_seconds is not None:
            if field and str(field).lower().replace('-', '_') in _DURATION_FRAME_FIELDS:
                value = _duration_to_frames(duration_seconds, source, item.mapping.nodeId, fps_value)
            elif field and str(field).lower().replace('-', '_') in _DURATION_SECOND_FIELDS:
                value = duration_seconds
        if field:
            node_inputs[field] = value

    if manifest.runtime.durationPolicy == 'dynamic' and duration_seconds is not None:
        return _apply_dynamic_duration(prompt, source, duration_seconds, fps_value)
    return None


def _detect_output_type(default_type: str, filename: str, media_format: str = '') -> str:
    suffix = Path(filename).suffix.lower()
    normalized_format = media_format.lower()
    if normalized_format.startswith('video/') or suffix in {'.mp4', '.webm', '.mov', '.mkv'}:
        return 'video'
    if normalized_format.startswith('audio/') or suffix in {'.wav', '.mp3', '.flac', '.m4a', '.ogg'}:
        return 'audio'
    return default_type


def _collect_outputs(db: Database, task_id: str, workflow_id: str, history: dict[str, Any], client: ComfyClient) -> list[dict[str, Any]]:
    output_dir = OUTPUT_ROOT / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, Any]] = []
    outputs = history.get('outputs') or {}
    for node_id, node_output in outputs.items():
        if not isinstance(node_output, dict):
            continue
        for key, output_type in (('images', 'image'), ('gifs', 'video'), ('videos', 'video'), ('audio', 'audio')):
            values = node_output.get(key) or []
            if not isinstance(values, list):
                continue
            for item in values:
                if not isinstance(item, dict) or not item.get('filename'):
                    continue
                filename = Path(str(item['filename'])).name
                detected_type = _detect_output_type(output_type, filename, str(item.get('format') or ''))
                raw = client.download_view(filename, str(item.get('subfolder') or ''), str(item.get('type') or 'output'))
                target = output_dir / filename
                target.write_bytes(raw)
                output_id = f'out-{uuid.uuid4().hex[:12]}'
                metadata = {'nodeId': str(node_id), 'source': item}
                with db.connect() as conn:
                    conn.execute(
                        'INSERT INTO outputs(id,task_id,workflow_id,type,file_path,thumbnail_path,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?)',
                        (output_id, task_id, workflow_id, detected_type, str(target), None, json.dumps(metadata, ensure_ascii=False), _now()),
                    )
                saved.append({'id': output_id, 'type': detected_type, 'file': str(target)})
    return saved
