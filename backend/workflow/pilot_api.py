from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.db import Database
from backend.models import GenerationTaskCreate
from backend.workflow.pilot import PilotRejected, create_pilot, pilot_detail, validate_pilot


def workflow_pilot_router(db: Database) -> APIRouter:
    router = APIRouter(prefix='/api/workflows', tags=['runtime-pilot'])

    @router.get('/{workflow_id}/pilot')
    def pilot_readiness(workflow_id: str):
        try:
            value = validate_pilot(db, workflow_id, {})
        except PilotRejected as exc:
            if exc.code != 'REQUIRED_INPUT_MISSING':
                raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': str(exc)}) from exc
            from backend.workflow.preflight import preflight_detail
            return {'allowed': True, 'preflight': preflight_detail(db, workflow_id, force_refresh=True), 'requiredInputsPending': True}
        return {'allowed': True, 'preflight': value['preflight'], 'requiredInputsPending': False}

    @router.post('/{workflow_id}/pilot-run')
    def run_pilot(workflow_id: str, payload: GenerationTaskCreate):
        try:
            task_id = create_pilot(db, workflow_id, payload)
        except PilotRejected as exc:
            raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': str(exc)}) from exc
        return {'taskId': task_id, 'status': 'WAITING', 'runtimeClone': True, 'strictSerial': True}

    @router.get('/pilot-runs/{task_id}')
    def get_pilot(task_id: str):
        result = pilot_detail(db, task_id)
        if result is None:
            raise HTTPException(status_code=404, detail='task_not_found')
        return result

    return router
