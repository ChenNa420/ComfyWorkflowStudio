from __future__ import annotations

import argparse
import json
from urllib.parse import urlencode
from urllib.request import urlopen


def get_json(base: str, path: str):
    with urlopen(base.rstrip('/') + path, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f'{path}: HTTP {response.status}')
        return json.loads(response.read().decode('utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description='ComfyWorkflowStudio Phase 1F knowledge smoke check')
    parser.add_argument('--base', default='http://127.0.0.1:8100')
    parser.add_argument('--query', default='video')
    parser.add_argument('--capability', default='image-to-video')
    args = parser.parse_args()

    health = get_json(args.base, '/api/health')
    stats = get_json(args.base, '/api/workflow-knowledge/stats')
    query = urlencode({'q': args.query, 'limit': 20})
    items = get_json(args.base, f'/api/workflow-knowledge?{query}')
    recommend_query = urlencode({'capability': args.capability, 'readyOnly': 'false', 'limit': 10})
    recommendations = get_json(args.base, f'/api/workflow-knowledge/recommendations?{recommend_query}')

    print('Phase:', health.get('phase'))
    print('Workflow packages:', stats.get('total'))
    print('Average completeness:', stats.get('averageCompleteness'))
    print('READY:', stats.get('ready'))
    print('NEEDS_ADAPTATION:', stats.get('needsAdaptation'))
    print('MISSING_DEPENDENCIES:', stats.get('missingDependencies'))
    print('Search results:', len(items))
    print('Recommendation results:', len(recommendations.get('items') or []))
    print('\nTop categories:')
    for item in (stats.get('categories') or [])[:12]:
        print(f"  {item['label']}: {item['count']}")
    print('\nTop recommendations:')
    for item in (recommendations.get('items') or [])[:10]:
        print(
            f"  {item['recommendationScore']:>3} | {item['health']:<20} | "
            f"{item['completeness']['score']:>3} | {item['name']}"
        )

    if stats.get('total', 0) <= 0:
        raise RuntimeError('No workflow packages discovered')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
