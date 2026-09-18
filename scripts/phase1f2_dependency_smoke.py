from __future__ import annotations

import argparse
import json
from urllib.request import urlopen


def get_json(base: str, path: str):
    with urlopen(base.rstrip('/') + path, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f'{path}: HTTP {response.status}')
        return json.loads(response.read().decode('utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description='ComfyWorkflowStudio Phase 1F-2 dependency center smoke check')
    parser.add_argument('--base', default='http://127.0.0.1:8100')
    args = parser.parse_args()

    summary = get_json(args.base, '/api/dependencies/summary')
    workflows = get_json(args.base, '/api/dependencies/workflows?limit=1000')
    models = get_json(args.base, '/api/dependencies/models?limit=5000')
    nodes = get_json(args.base, '/api/dependencies/nodes?limit=5000')
    reviews = get_json(args.base, '/api/manifest-review?limit=1000')

    print('ComfyUI connected:', summary.get('connected'))
    print('ComfyUI URL:', summary.get('comfyUiUrl'))
    for key, value in (summary.get('summary') or {}).items():
        print(f'{key}: {value}')
    print('Workflow dependency rows:', len(workflows.get('items') or []))
    print('Model rows:', len(models.get('items') or []))
    print('Node rows:', len(nodes.get('items') or []))
    print('Manifest review rows:', len(reviews))
    print('Review rows with safe proposals:', sum(1 for item in reviews if item.get('proposalCount', 0) > 0))

    if not summary.get('connected'):
        raise RuntimeError('ComfyUI is offline; real dependency verification cannot be accepted')
    if summary.get('summary', {}).get('workflows', 0) <= 0:
        raise RuntimeError('No workflow packages discovered')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
