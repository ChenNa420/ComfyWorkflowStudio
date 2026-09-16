from __future__ import annotations

import json
import threading
from typing import Any

from backend.comfy.runtime import create_task, start_task
from backend.db import Database
from backend.models import GenerationTaskCreate, WorkflowManifest
from backend.workflow.preflight import PREFLIGHT_CERTIFIED, preflight_detail

ACTIVE = ('WAITING', 'PREPARING', 'SUBMITTING', 'QUEUED', 'RUNNING')
_PILOT_GATE = threading.Lock()


class PilotRejected(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _manifest(db: Database, workflow_id: str) -> WorkflowManifest:
    with db.connect() as conn:
        row = conn.execute('SELECT manifest_json FROM workflows WHERE id=?', (workflow_id,)).fetchone()
    if row is None:
        raise PilotRejected('WORKFLOW_NOT_FOUND', 'workflow_not_found', 404)
    return WorkflowManifest.model_validate(json.loads(row['manifest_json']))


def validate_pilot(db: Database, workflow_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    preflight = preflight_detail(db, workflow_id, force_refresh=True)
    if preflight is None:
        raise PilotRejected('WORKFLOW_NOT_FOUND', 'workflow_not_found', 404)
    if preflight['status'] != PREFLIGHT_CERTIFIED:
        raise PilotRejected(str(preflight['status']), '当前 Workflow 尚未通过 Runtime Preflight Certification。')
    if preflight.get('dependencyStatus') != 'READY':
        raise PilotRejected('DEPENDENCY_NOT_READY', 'Workflow runtime dependencies are not ready.')
    manifest = _manifest(db, workflow_id)
    missing = [item.key for item in manifest.inputs if item.required and not inputs.get(item.key)]
    if missing:
        raise PilotRejected('REQUIRED_INPUT_MISSING', f"Missing required runtime inputs: {', '.join(missing)}", 422)
    return {'preflight': preflight, 'manifest': manifest}


def create_pilot(db: Database, workflow_id: str, payload: GenerationTaskCreate) -> str:
    with _PILOT_GATE:
        validated = validate_pilot(db, workflow_id, payload.inputs)
        with db.connect() as conn:
            marks = ','.join('?' for _ in ACTIVE)
            active = conn.execute(
                f'SELECT id FROM generation_tasks WHERE status IN ({marks}) ORDER BY created_at LIMIT 1', ACTIVE
            ).fetchone()
        if active:
            raise PilotRejected('PILOT_ACTIVE', f"Pilot execution already active: {active['id']}")
        payload.workflowId = workflow_id
        task_id = create_task(db, payload, start=False)
        from backend.comfy.runtime import _event
        _event(db, task_id, 'PILOT_AUTHORIZED', 'Fresh preflight certified before runtime submission', {
            'status': validated['preflight']['status'], 'sourceFormat': validated['preflight']['sourceFormat'],
            'runtimeClone': True, 'strictSerial': True,
        })
        start_task(db, task_id)
        return task_id


def pilot_detail(db: Database, task_id: str) -> dict[str, Any] | None:
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM generation_tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            return None
        outputs = conn.execute('SELECT * FROM outputs WHERE task_id=? ORDER BY created_at,id', (task_id,)).fetchall()
    result = dict(row)
    result['outputs'] = [dict(item) for item in outputs]
    return result
