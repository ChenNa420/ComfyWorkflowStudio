from __future__ import annotations

import argparse
import json
from urllib.parse import urlencode
from urllib.request import urlopen


def get_json(base: str, path: str):
    with urlopen(base.rstrip('/') + path, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f'{path}: HTTP {response.status}')
        return json.loads(response.read().decode('utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description='Phase 1G-3 runtime preflight smoke check')
    parser.add_argument('--base', default='http://127.0.0.1:8100')
    parser.add_argument('--capability', default='image-to-video')
    args = parser.parse_args()

    health = get_json(args.base, '/api/health')
    all_report = get_json(args.base, '/api/readiness/preflight?forceRefresh=true&limit=1000')
    focused = get_json(
        args.base,
        '/api/readiness/preflight?'
        + urlencode({'capability': args.capability, 'limit': 1000}),
    )

    print('Phase:', health.get('phase'), '/', health.get('subphase'))
    print('Connected:', all_report.get('connected'))
    print('Workflows:', all_report.get('summary', {}).get('workflows'))
    print('Certified:', all_report.get('summary', {}).get('certified'))
    print('Needs review:', all_report.get('summary', {}).get('needsReview'))
    print('Blocked dependencies:', all_report.get('summary', {}).get('blockedDependencies'))
    print('Offline:', all_report.get('summary', {}).get('offline'))
    print('\nTop error codes:')
    for item in (all_report.get('summary', {}).get('errorCodes') or [])[:10]:
        print(f"  {item['key']}: {item['count']}")

    print(f'\n{args.capability}:')
    print('  Workflows:', focused.get('summary', {}).get('workflows'))
    print('  Certified:', focused.get('summary', {}).get('certified'))
    print('  Needs review:', focused.get('summary', {}).get('needsReview'))
    print('  Blocked dependencies:', focused.get('summary', {}).get('blockedDependencies'))

    if all_report.get('connected'):
        for item in all_report.get('items') or []:
            if item.get('writeMode') is not False or item.get('submitsPrompt') is not False:
                raise RuntimeError(f"Unsafe preflight flags for {item.get('workflowId')}")
    else:
        certified = int(all_report.get('summary', {}).get('certified') or 0)
        if certified:
            raise RuntimeError('Offline preflight returned CERTIFIED workflows')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
