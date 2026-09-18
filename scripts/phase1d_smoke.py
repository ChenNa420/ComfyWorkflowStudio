from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

TERMINAL = {'SUCCEEDED', 'FAILED', 'UNKNOWN', 'NEEDS_REVIEW', 'CANCELLED'}


def request_json(base: str, path: str, method: str = 'GET', payload: dict[str, Any] | None = None) -> Any:
    body = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base.rstrip('/') + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'{method} {path} -> HTTP {exc.code}: {detail}') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'无法连接 {base}: {exc}') from exc


def choose_workflow(items: list[dict[str, Any]], query: str) -> dict[str, Any]:
    key = query.lower().strip()
    exact = [item for item in items if str(item.get('id', '')).lower() == key]
    if exact:
        return exact[0]
    matches = [
        item for item in items
        if key in f"{item.get('id', '')} {item.get('name', '')} {item.get('category', '')}".lower()
    ]
    if not matches:
        raise RuntimeError(f'找不到工作流: {query}')
    preferred = [item for item in matches if item.get('category') in {'image-to-video', 'first-last-video'}]
    return (preferred or matches)[0]


def first_input(manifest: dict[str, Any], purposes: set[str], fallback_type: str | None = None) -> dict[str, Any] | None:
    inputs = manifest.get('inputs') or []
    for item in inputs:
        if item.get('purpose') in purposes:
            return item
    if fallback_type:
        for item in inputs:
            if item.get('type') == fallback_type:
                return item
    return None


def parameter_key(manifest: dict[str, Any], candidates: set[str]) -> str | None:
    for item in manifest.get('parameters') or []:
        if str(item.get('key', '')).lower() in candidates:
            return str(item['key'])
        strategy = str((item.get('mapping') or {}).get('strategy') or '')
        if 'duration' in candidates and strategy == 'duration-to-frames':
            return str(item['key'])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description='ComfyWorkflowStudio Phase 1D local smoke test')
    parser.add_argument('--base', default='http://127.0.0.1:8100')
    parser.add_argument('--workflow', default='minimax', help='工作流 ID 或名称关键字')
    parser.add_argument('--first-frame', help='本地首帧图片绝对路径')
    parser.add_argument('--prompt', default='The subject makes one clear natural movement. Keep identity, scene and props consistent.')
    parser.add_argument('--negative', default='identity drift, duplicated props, disappearing objects, generated text, watermark')
    parser.add_argument('--duration', type=float, default=5.0)
    parser.add_argument('--fps', type=float, default=24.0)
    parser.add_argument('--seed', type=int, default=-1)
    parser.add_argument('--run', action='store_true', help='真正提交生成；默认只做环境/Manifest/依赖检查')
    parser.add_argument('--timeout', type=int, default=1200)
    args = parser.parse_args()

    print('== Phase 1D smoke ==')
    health = request_json(args.base, '/api/health')
    print('API:', health.get('status'), 'phase=', health.get('phase'))
    print('ComfyUI:', health.get('comfyUi'), health.get('comfyUiUrl'))
    if health.get('status') != 'ok':
        raise RuntimeError('API health 不是 ok')

    workflows = request_json(args.base, '/api/workflows')
    if not workflows:
        raise RuntimeError('工作流库为空，请先从“导入工作流”导入 MiniMax H3 工作流')
    workflow = choose_workflow(workflows, args.workflow)
    workflow_id = workflow['id']
    print('Workflow:', workflow_id, '-', workflow.get('name'))

    manifest = request_json(args.base, f"/api/workflows/{urllib.parse.quote(workflow_id, safe='')}/manifest")
    compatibility = request_json(args.base, f"/api/workflows/{urllib.parse.quote(workflow_id, safe='')}/compatibility")
    print('Compatibility:', compatibility.get('status'))
    missing_nodes = compatibility.get('missingNodes') or []
    if missing_nodes:
        print('Missing nodes:', ', '.join(missing_nodes))

    image_input = first_input(manifest, {'video-start-frame', 'source-image'}, 'image')
    prompt_input = first_input(manifest, {'prompt'})
    negative_input = first_input(manifest, {'negative-prompt'})
    duration_key = parameter_key(manifest, {'duration', 'seconds', 'video_duration'})
    fps_key = parameter_key(manifest, {'fps', 'frame_rate', 'framerate'})
    seed_key = parameter_key(manifest, {'seed'})

    print('Input mapping:')
    print('  first frame =', image_input.get('key') if image_input else '(未识别)')
    print('  prompt      =', prompt_input.get('key') if prompt_input else '(未识别)')
    print('  negative    =', negative_input.get('key') if negative_input else '(可选/未识别)')
    print('  duration    =', duration_key or '(未识别)')
    print('  fps         =', fps_key or '(未识别)')
    print('  seed        =', seed_key or '(未识别)')

    if not args.run:
        print('\nDRY RUN 完成。要实际生成，请增加 --run --first-frame D:\\path\\image.png')
        return 0

    if health.get('comfyUi') != 'connected':
        raise RuntimeError('ComfyUI 当前不可连接，不能执行真实生成')
    if compatibility.get('status') != 'READY':
        raise RuntimeError('工作流依赖未通过，不能执行真实生成')
    if image_input is None:
        raise RuntimeError('Manifest 没有识别首帧/图片输入，请先在工作流适配页确认')
    if not args.first_frame:
        raise RuntimeError('--run 时必须提供 --first-frame')
    frame = Path(args.first_frame).expanduser().resolve()
    if not frame.is_file():
        raise RuntimeError(f'首帧不存在: {frame}')

    inputs: dict[str, Any] = {str(image_input['key']): str(frame)}
    if prompt_input:
        inputs[str(prompt_input['key'])] = args.prompt
    if negative_input:
        inputs[str(negative_input['key'])] = args.negative

    parameters: dict[str, Any] = {}
    if duration_key:
        parameters[duration_key] = args.duration
    if fps_key:
        parameters[fps_key] = args.fps
    if seed_key:
        parameters[seed_key] = args.seed

    payload = {
        'workflowId': workflow_id,
        'clientApp': 'Phase1DSmoke',
        'projectId': 'phase1d-acceptance',
        'inputs': inputs,
        'parameters': parameters,
    }
    created = request_json(args.base, '/api/tasks', 'POST', payload)
    task_id = created['taskId']
    print('Task:', task_id)

    deadline = time.time() + args.timeout
    last_status = None
    while time.time() < deadline:
        task = request_json(args.base, f'/api/tasks/{task_id}')
        status = str(task.get('status'))
        if status != last_status:
            print(f"  {status:12} progress={float(task.get('progress') or 0):.0%}")
            last_status = status
        if status in TERMINAL:
            events = request_json(args.base, f'/api/tasks/{task_id}/events')
            duration_events = [item for item in events if item.get('event') == 'DURATION_APPLIED']
            if duration_events:
                print('Duration:', duration_events[-1].get('message'))
            if status != 'SUCCEEDED':
                print('Error:', task.get('error'))
                return 2
            outputs = task.get('outputs') or []
            print('Outputs:', len(outputs))
            for item in outputs:
                print(' ', item.get('type'), item.get('file_path'))
            print('PHASE 1D REAL GENERATION: PASS')
            return 0
        time.sleep(2)

    raise RuntimeError(f'任务 {task_id} 在 {args.timeout}s 内未进入终态')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - command-line validation boundary
        print('FAIL:', exc, file=sys.stderr)
        raise SystemExit(1)
