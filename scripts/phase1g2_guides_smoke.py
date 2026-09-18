from __future__ import annotations

import argparse
import json
from urllib.parse import urlencode
from urllib.request import urlopen

NON_EXECUTION = {'MarkdownNote', 'Note', 'PixaromaNote', 'PixaromaLabel'}


def get_json(base: str, path: str):
    with urlopen(base.rstrip('/') + path, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f'{path}: HTTP {response.status}')
        return json.loads(response.read().decode('utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description='Phase 1G-2 execution-aware remediation smoke check')
    parser.add_argument('--base', default='http://127.0.0.1:8100')
    parser.add_argument('--capability', default='image-to-video')
    args = parser.parse_args()

    health = get_json(args.base, '/api/health')
    plan = get_json(args.base, '/api/readiness/plan?forceRefresh=true&limit=200')
    guides = get_json(args.base, '/api/remediation-guides?limit=50')
    cap_query = urlencode({'capability': args.capability, 'limit': 50})
    capability_guides = get_json(args.base, f'/api/remediation-guides?{cap_query}')
    dependencies = get_json(args.base, '/api/dependencies/summary')

    print('Phase:', health.get('phase'), health.get('subphase'))
    print('Connected:', plan.get('connected'))
    print('Ready:', plan.get('summary', {}).get('ready'))
    print('Blocked:', plan.get('summary', {}).get('blocked'))
    print('Near ready:', plan.get('summary', {}).get('nearReady'))
    print('Ignored node types:', dependencies.get('summary', {}).get('ignoredNodeTypes'))
    print('Ignored node occurrences:', dependencies.get('summary', {}).get('ignoredNodeOccurrences'))
    print('Guides:', guides.get('summary', {}).get('guides'))
    print('High-confidence guides:', guides.get('summary', {}).get('withHighConfidenceAction'))
    print(f'{args.capability} guides:', capability_guides.get('summary', {}).get('guides'))

    blocker_names = {str(item.get('name')) for item in plan.get('topBlockers') or []}
    invalid = blocker_names & NON_EXECUTION
    if invalid:
        raise RuntimeError(f'Non-execution nodes still block readiness: {sorted(invalid)}')

    if not plan.get('connected'):
        if guides.get('guides'):
            raise RuntimeError('Offline mode returned remediation guides')
        return 0

    print('\nTop remediation guides:')
    for item in (guides.get('guides') or [])[:10]:
        print(
            f"  {item['kind']:<5} unlock={item['unlockCount']:<3} affected={item['affectedCount']:<3} "
            f"confidence={item['confidence']:<6} action={item['action']:<26} {item['name']}"
        )
        if item.get('sourceUrl'):
            print('      source:', item['sourceUrl'])
        elif item.get('sourceUrls'):
            print('      source:', item['sourceUrls'][0]['url'])
        elif item.get('declaredPaths'):
            print('      path:', item['declaredPaths'][0]['declaredPath'])

    if any(item.get('writeMode') is not False for item in guides.get('guides') or []):
        raise RuntimeError('A remediation guide is not read-only')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
