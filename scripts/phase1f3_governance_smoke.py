from __future__ import annotations

import argparse
import json
from urllib import request
from urllib.parse import urlencode


def get_json(base: str, path: str):
    with request.urlopen(base.rstrip('/') + path, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f'{path}: HTTP {response.status}')
        return json.loads(response.read().decode('utf-8'))


def post_json(base: str, path: str, payload: dict):
    raw = json.dumps(payload).encode('utf-8')
    req = request.Request(
        base.rstrip('/') + path,
        data=raw,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with request.urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f'{path}: HTTP {response.status}')
        return json.loads(response.read().decode('utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description='ComfyWorkflowStudio Phase 1F-3 governance smoke check')
    parser.add_argument('--base', default='http://127.0.0.1:8100')
    args = parser.parse_args()

    health = get_json(args.base, '/api/health')
    dependency = get_json(args.base, '/api/dependencies/summary?forceRefresh=true')
    knowledge = get_json(args.base, '/api/workflow-knowledge/stats')
    reviews = get_json(args.base, '/api/manifest-review?needsProposal=true&limit=10')

    model_types = dependency.get('summary', {}).get('modelTypes') or []
    print('Phase:', health.get('phase'))
    print('Dependency connected:', dependency.get('connected'))
    print('Workflow knowledge total:', knowledge.get('total'))
    print('Knowledge health:', knowledge.get('health'))
    print('Dependency states:', knowledge.get('dependencyStates'))
    print('Model types:')
    for item in model_types:
        print(f"  {item.get('key')}: {item.get('count')}")

    if reviews:
        ids = [item['workflowId'] for item in reviews[:3]]
        batch = post_json(args.base, '/api/manifest-review/batch-preview', {'workflowIds': ids})
        print('Batch preview:', batch.get('found'), 'workflows /', batch.get('proposalCount'), 'proposals')
        print('Batch write mode:', batch.get('writeMode'))
        history = get_json(args.base, f"/api/manifest-history/{ids[0]}")
        print('Manifest history versions:', len(history.get('versions') or []))
    else:
        print('No safe Manifest proposals currently available.')

    checkpoint_query = urlencode({'modelType': 'checkpoint', 'limit': 5})
    checkpoint_models = get_json(args.base, f'/api/dependencies/models?{checkpoint_query}')
    print('Checkpoint sample count:', len(checkpoint_models.get('items') or []))

    if health.get('phase') != '1F':
        raise RuntimeError('Unexpected health phase')
    if dependency.get('connected') is not True:
        raise RuntimeError('ComfyUI is not connected')
    if knowledge.get('total', 0) <= 0:
        raise RuntimeError('Workflow knowledge is empty')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
