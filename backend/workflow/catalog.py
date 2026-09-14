from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from backend.db import Database
from backend.models import WorkflowManifest
from backend.workflow.analyzer import analyze_workflow
from backend.workflow.manifest import LOCAL_WORKFLOW_ROOT, save_manifest


@dataclass
class ImportItem:
    filename: str
    data: dict[str, Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(raw: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def iter_import_items(filename: str, raw: bytes) -> Iterable[ImportItem]:
    lower = filename.lower()
    if lower.endswith('.json'):
        value = _safe_json_loads(raw)
        if value is not None:
            yield ImportItem(filename=Path(filename).name, data=value)
        return

    if lower.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for member in archive.infolist():
                if member.is_dir() or not member.filename.lower().endswith('.json'):
                    continue
                # Third-party archives are never extracted. We only inspect JSON in memory.
                if member.file_size > 50 * 1024 * 1024:
                    continue
                value = _safe_json_loads(archive.read(member))
                if value is not None:
                    yield ImportItem(filename=member.filename, data=value)


def _existing_hashes() -> dict[str, str]:
    result: dict[str, str] = {}
    if not LOCAL_WORKFLOW_ROOT.exists():
        return result
    for path in LOCAL_WORKFLOW_ROOT.glob('*/analysis.json'):
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        content_hash = str(payload.get('hash') or '')
        workflow_id = str(payload.get('workflowId') or path.parent.name)
        if content_hash:
            result[content_hash] = workflow_id
    return result


def _manifest_from_analysis(workflow_id: str, analysis: dict[str, Any], source_name: str) -> WorkflowManifest:
    raw_inputs = []
    for item in analysis.get('inputs', []):
        raw_inputs.append({
            'key': item.get('key') or 'input',
            'label': item.get('label') or '输入',
            'type': item.get('type') or 'text',
            'required': bool(item.get('required', True)),
            'purpose': item.get('purpose'),
            'description': item.get('description') or '',
            'help': item.get('help') or '',
            'recommended': item.get('recommended') or [],
            'accept': item.get('accept') or [],
            'mapping': item.get('mapping') or {},
        })

    raw_parameters = []
    for item in analysis.get('parameters', []):
        raw_parameters.append({key: value for key, value in item.items() if key in {
            'key', 'label', 'type', 'default', 'min', 'max', 'step', 'unit', 'options', 'description', 'mapping'
        }})

    category = str(analysis.get('category') or 'other')
    is_video = 'video' in category
    return WorkflowManifest.model_validate({
        'schemaVersion': '1.0',
        'workflowId': workflow_id,
        'name': analysis.get('name') or workflow_id,
        'category': category,
        'description': _default_description(category),
        'difficulty': 'medium',
        'source': {'name': source_name, 'url': ''},
        'capabilities': analysis.get('capabilities') or [],
        'recommendedFor': _recommended_for(category),
        'notRecommendedFor': [],
        'inputs': raw_inputs,
        'parameters': raw_parameters,
        'outputs': analysis.get('outputs') or [],
        'dependencies': analysis.get('dependencies') or {'models': [], 'customNodes': []},
        'runtime': {
            'executionMode': 'serial',
            'durationPolicy': 'dynamic' if is_video else 'none',
            'allowRetry': True,
            'retryUnknown': False,
            'preserveOriginalWorkflow': True,
            'outputTimeout': 900,
        },
        'guide': {
            'summary': _default_description(category),
            'steps': _default_steps(category, raw_inputs),
            'promptTips': ['明确主体动作', '描述环境变化', '需要时说明摄影机运动'] if is_video else [],
            'warnings': ['自动识别结果需要在适配向导中确认后再投入批量生产。'],
        },
    })


def _default_description(category: str) -> str:
    mapping = {
        'image-to-video': '使用一张或多张图片作为条件生成视频。',
        'first-last-video': '使用首帧与尾帧控制视频起止状态。',
        'text-to-video': '根据文本提示生成视频。',
        'text-to-image': '根据文本提示生成图片。',
        'image-edit': '对输入图片进行编辑或重绘。',
        'controlnet': '使用 Pose、Depth、Lineart 等控制条件生成图片或视频。',
        'tts': '把文本转换为语音。',
        'audio': '生成或处理音乐与音频。',
        '3d': '根据图片或文本生成 3D 相关结果。',
    }
    return mapping.get(category, '从 ComfyUI 导入的工作流，等待补充完整使用说明。')


def _recommended_for(category: str) -> list[str]:
    if category in {'image-to-video', 'first-last-video'}:
        return ['动画镜头', '人物或动物动作', '短视频']
    if category == 'tts':
        return ['配音', '对白生成']
    if category in {'text-to-image', 'image-edit', 'controlnet'}:
        return ['首帧', '角色图', '场景图']
    return []


def _default_steps(category: str, inputs: list[dict[str, Any]]) -> list[str]:
    steps = [f"准备 {item.get('label', '输入素材')}" for item in inputs if item.get('required')]
    if 'video' in category:
        steps.append('确认视频时长和生成参数')
    steps.append('提交任务并等待 ComfyUI 完成')
    return steps


def import_payload(filename: str, raw: bytes, db: Database, source_name: str = 'Local Import') -> dict[str, Any]:
    existing = _existing_hashes()
    imported: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    invalid = 0

    try:
        items = list(iter_import_items(filename, raw))
    except (zipfile.BadZipFile, RuntimeError):
        return {'ok': False, 'error': 'invalid_archive', 'imported': [], 'duplicates': [], 'resources': [], 'invalid': 1}

    for item in items:
        analysis = analyze_workflow(item.data, item.filename)
        if analysis['format'] == 'resource-json':
            resources.append({'filename': item.filename, 'hash': analysis['hash'], 'name': analysis['name']})
            continue

        content_hash = analysis['hash']
        if content_hash in existing:
            duplicates.append({'filename': item.filename, 'workflowId': existing[content_hash], 'hash': content_hash})
            continue

        base_id = str(analysis['slug'])
        workflow_id = f"{base_id}-{content_hash[:8]}"
        package_dir = LOCAL_WORKFLOW_ROOT / workflow_id
        package_dir.mkdir(parents=True, exist_ok=True)
        original_path = package_dir / 'original.json'
        manifest_path = package_dir / 'manifest.json'
        analysis_path = package_dir / 'analysis.json'

        original_path.write_text(json.dumps(item.data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        manifest = _manifest_from_analysis(workflow_id, analysis, source_name)
        save_manifest(manifest, manifest_path)
        analysis_payload = dict(analysis)
        analysis_payload['workflowId'] = workflow_id
        analysis_payload['sourceFilename'] = item.filename
        analysis_path.write_text(json.dumps(analysis_payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

        now = _now()
        with db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workflows(
                    id, name, category, source, source_url, description, difficulty,
                    original_path, api_workflow_path, cover_path, manifest_json,
                    manifest_version, enabled, compatibility_status, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    workflow_id,
                    manifest.name,
                    manifest.category,
                    manifest.source.name,
                    manifest.source.url,
                    manifest.description,
                    manifest.difficulty,
                    str(original_path),
                    str(original_path) if analysis['format'] == 'api-workflow' else None,
                    None,
                    json.dumps(manifest.model_dump(mode='json'), ensure_ascii=False),
                    1,
                    1,
                    'NEEDS_ADAPTER' if analysis['format'] == 'ui-workflow' else 'READY_FOR_DEPENDENCY_CHECK',
                    now,
                    now,
                ),
            )

        existing[content_hash] = workflow_id
        imported.append({
            'filename': item.filename,
            'workflowId': workflow_id,
            'format': analysis['format'],
            'category': analysis['category'],
            'nodeCount': analysis['nodeCount'],
            'inputs': len(analysis.get('inputs') or []),
            'models': len((analysis.get('dependencies') or {}).get('models') or []),
            'customNodes': len((analysis.get('dependencies') or {}).get('customNodes') or []),
        })

    if not items:
        invalid = 1

    return {
        'ok': True,
        'source': filename,
        'scanned': len(items),
        'imported': imported,
        'duplicates': duplicates,
        'resources': resources,
        'invalid': invalid,
    }
