from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from backend.comfy.runtime import create_task, start_task
from backend.db import Database
from backend.models import GenerationTaskCreate
from backend.workflow.pilot import ACTIVE, PilotRejected, _manifest, validate_pilot

from backend.workflow.execution_gate import EXECUTION_CREATE_LOCK


def run_schema(db: Database, workflow_id: str) -> dict[str, Any]:
    try:
        validated = validate_pilot(db, workflow_id, {})
        pending = False
    except PilotRejected as exc:
        if exc.code != 'REQUIRED_INPUT_MISSING':
            raise
        from backend.workflow.preflight import preflight_detail
        validated = {'manifest': _manifest(db, workflow_id), 'preflight': preflight_detail(db, workflow_id, force_refresh=True)}
        pending = True
    return {
        'allowed': True,
        'requiredInputsPending': pending,
        'manifest': validated['manifest'].model_dump(mode='json'),
        'preflight': validated['preflight'],
        'runtimeClone': True,
        'strictSerial': True,
    }


def create_run(db: Database, workflow_id: str, payload: GenerationTaskCreate) -> str:
    with EXECUTION_CREATE_LOCK:
        validated = validate_pilot(db, workflow_id, payload.inputs)
        with db.connect() as conn:
            marks = ','.join('?' for _ in ACTIVE)
            active = conn.execute(
                f'SELECT id FROM generation_tasks WHERE status IN ({marks}) ORDER BY created_at LIMIT 1', ACTIVE
            ).fetchone()
        if active:
            raise PilotRejected('RUN_ACTIVE', f"Production run already active: {active['id']}")
        payload.workflowId = workflow_id
        task_id = create_task(db, payload, start=False)
        from backend.comfy.runtime import _event
        _event(db, task_id, 'RUN_AUTHORIZED', 'Fresh certification checked for production run', {
            'status': validated['preflight']['status'], 'sourceFormat': validated['preflight']['sourceFormat'],
            'runtimeClone': True, 'strictSerial': True,
        })
        start_task(db, task_id)
        return task_id


def run_detail(db: Database, task_id: str) -> dict[str, Any] | None:
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM generation_tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            return None
        outputs = conn.execute('SELECT * FROM outputs WHERE task_id=? ORDER BY created_at,id', (task_id,)).fetchall()
        events = conn.execute('SELECT event,message,created_at FROM generation_task_events WHERE task_id=? ORDER BY id', (task_id,)).fetchall()
    result = dict(row)
    result['outputs'] = [dict(item) for item in outputs]
    result['events'] = [dict(item) for item in events]
    for key in ('inputs_json', 'parameters_json'):
        result[key.removesuffix('_json')] = json.loads(result.get(key) or '{}')
    if result.get('started_at') and result.get('finished_at'):
        try:
            result['durationSeconds'] = round((datetime.fromisoformat(result['finished_at']) - datetime.fromisoformat(result['started_at'])).total_seconds(), 2)
        except ValueError:
            result['durationSeconds'] = None
    return result


def list_runs(db: Database, workflow_id: str, limit: int = 10) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT t.* FROM generation_tasks t WHERE t.workflow_id=? AND EXISTS(
                 SELECT 1 FROM generation_task_events e WHERE e.task_id=t.id AND e.event='RUN_AUTHORIZED')
                 ORDER BY t.created_at DESC LIMIT ?""", (workflow_id, max(1, min(limit, 100)))
        ).fetchall()
    return [dict(row) for row in rows]


def rerun(db: Database, task_id: str) -> str:
    detail = run_detail(db, task_id)
    if detail is None:
        raise PilotRejected('TASK_NOT_FOUND', 'task_not_found', 404)
    payload = GenerationTaskCreate(
        workflowId=detail['workflow_id'], clientApp=detail.get('client_app'), projectId=detail.get('project_id'),
        episodeId=detail.get('episode_id'), shotId=detail.get('shot_id'),
        inputs=detail['inputs'], parameters=detail['parameters'],
    )
    return create_run(db, detail['workflow_id'], payload)
