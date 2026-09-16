from __future__ import annotations

import argparse
import json
from urllib.parse import urlencode
from urllib.request import urlopen


def get_json(base: str, path: str):
    with urlopen(base.rstrip('/') + path, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f'{path}: HTTP {response.status}')
        return json.loads(response.read().decode('utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description='Phase 1G readiness remediation smoke check')
    parser.add_argument('--base', default='http://127.0.0.1:8100')
    parser.add_argument('--capability', default='image-to-video')
    args = parser.parse_args()

    health = get_json(args.base, '/api/health')
    plan = get_json(args.base, '/api/readiness/plan?forceRefresh=true&limit=20')
    cap_query = urlencode({'capability': args.capability, 'limit': 20})
    capability_plan = get_json(args.base, f'/api/readiness/plan?{cap_query}')

    print('Phase:', health.get('phase'))
    print('Connected:', plan.get('connected'))
    print('Ready:', plan.get('summary', {}).get('ready'))
    print('Blocked:', plan.get('summary', {}).get('blocked'))
    print('Near ready:', plan.get('summary', {}).get('nearReady'))
    print('Model blockers:', plan.get('summary', {}).get('modelBlockers'))
    print('Node blockers:', plan.get('summary', {}).get('nodeBlockers'))
    print('Top 10 unlock potential:', plan.get('summary', {}).get('topUnlockPotential'))
    print(f"\nCapability: {args.capability}")
    print('Workflows:', capability_plan.get('summary', {}).get('workflows'))
    print('Ready:', capability_plan.get('summary', {}).get('ready'))
    print('Blocked:', capability_plan.get('summary', {}).get('blocked'))
    print('Near ready:', capability_plan.get('summary', {}).get('nearReady'))
    print('\nTop blockers:')
    for item in (plan.get('topBlockers') or [])[:10]:
        print(f"  {item['kind']:<5} unlock={item['unlockCount']:<3} affected={item['affectedCount']:<3} {item['name']}")

    if health.get('phase') != '1G':
        raise RuntimeError('API phase is not 1G')
    if plan.get('connected') and plan.get('summary', {}).get('workflows', 0) <= 0:
        raise RuntimeError('No workflows in readiness plan')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
