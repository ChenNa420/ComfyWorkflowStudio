from fastapi import APIRouter, HTTPException

from backend.db import Database
from backend.models import GenerationTaskCreate
from backend.workflow.pilot import PilotRejected
from backend.workflow.runs import create_run, list_runs, rerun, run_detail, run_schema


def workflow_runs_router(db: Database) -> APIRouter:
    router = APIRouter(prefix='/api/workflows', tags=['production-runs'])

    def rejected(exc: PilotRejected):
        raise HTTPException(status_code=exc.status_code, detail={'code': exc.code, 'message': str(exc)}) from exc

    @router.get('/{workflow_id}/run-schema')
    def schema(workflow_id: str):
        try: return run_schema(db, workflow_id)
        except PilotRejected as exc: rejected(exc)

    @router.post('/{workflow_id}/runs')
    def create(workflow_id: str, payload: GenerationTaskCreate):
        try: task_id = create_run(db, workflow_id, payload)
        except PilotRejected as exc: rejected(exc)
        return {'taskId': task_id, 'status': 'WAITING', 'runtimeClone': True, 'strictSerial': True}

    @router.get('/{workflow_id}/runs')
    def recent(workflow_id: str, limit: int = 10):
        return list_runs(db, workflow_id, limit)

    @router.get('/runs/{task_id}')
    def detail(task_id: str):
        value = run_detail(db, task_id)
        if value is None: raise HTTPException(status_code=404, detail='task_not_found')
        return value

    @router.post('/runs/{task_id}/rerun')
    def repeat(task_id: str):
        try: new_id = rerun(db, task_id)
        except PilotRejected as exc: rejected(exc)
        return {'taskId': new_id, 'status': 'WAITING', 'rerunOf': task_id}

    return router
