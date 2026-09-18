from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def api(base: str, path: str, payload=None):
    raw = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=raw, headers={'Content-Type': 'application/json'}, method='POST' if raw else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=90) as response: return response.status, json.load(response)
    except urllib.error.HTTPError as exc: return exc.code, json.load(exc)


def snapshot():
    names = {'manifest.json', 'original.json', 'workflow-api.json'}
    files = sorted(p for p in (ROOT / 'storage' / 'workflow-packages').rglob('*') if p.is_file() and p.name in names)
    digest = hashlib.sha256()
    for path in files: digest.update(str(path.relative_to(ROOT)).encode()); digest.update(path.read_bytes())
    with sqlite3.connect(ROOT / 'database' / 'studio.sqlite3') as conn:
        schema = list(conn.execute("SELECT name,sql FROM sqlite_master WHERE type IN ('table','index') ORDER BY name"))
        counts = {table: conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('workflows','workflow_bindings','generation_tasks','generation_task_events','outputs')}
    return {'protectedFiles':len(files),'protectedBytes':sum(p.stat().st_size for p in files),'protectedDigest':digest.hexdigest(),'schemaDigest':hashlib.sha256(json.dumps(schema).encode()).hexdigest(),'counts':counts}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--base',default='http://127.0.0.1:8100'); parser.add_argument('--workflow'); parser.add_argument('--inputs',default='{}'); parser.add_argument('--parameters',default='{}'); parser.add_argument('--reuse-latest-success',action='store_true'); parser.add_argument('--run',action='store_true'); args=parser.parse_args()
    print('SNAPSHOT',json.dumps(snapshot(),indent=2))
    print('HEALTH',api(args.base,'/api/health'))
    if not args.workflow: return
    print('READINESS',api(args.base,f'/api/workflows/{args.workflow}/pilot'))
    if not args.run: return
    inputs=json.loads(args.inputs); parameters=json.loads(args.parameters)
    if args.reuse_latest_success:
        with sqlite3.connect(ROOT/'database'/'studio.sqlite3') as conn:
            row=conn.execute("SELECT inputs_json,parameters_json FROM generation_tasks WHERE workflow_id=? AND status='SUCCEEDED' ORDER BY created_at DESC LIMIT 1",(args.workflow,)).fetchone()
        if not row: raise SystemExit('No historical SUCCEEDED task to reuse')
        inputs=json.loads(row[0]); parameters=json.loads(row[1])
    payload={'workflowId':args.workflow,'clientApp':'phase1g4-smoke','inputs':inputs,'parameters':parameters}
    status,data=api(args.base,f'/api/workflows/{args.workflow}/pilot-run',payload); print('SUBMIT',status,data)
    if status != 200: return
    task=data['taskId']
    while True:
        _,detail=api(args.base,f'/api/workflows/pilot-runs/{task}'); print('TASK',detail.get('status'),detail.get('prompt_id'))
        if detail.get('status') in {'SUCCEEDED','FAILED','UNKNOWN','NEEDS_REVIEW'}: print(json.dumps(detail,ensure_ascii=False,indent=2)); break
        time.sleep(2)
    print('FINAL_SNAPSHOT',json.dumps(snapshot(),indent=2))


if __name__=='__main__': main()
