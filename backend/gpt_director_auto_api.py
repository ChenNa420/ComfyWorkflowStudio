from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.db import ROOT
from backend.gpt_director_auto import GPTDirectorAutoError, GPTDirectorAutoService


def gpt_director_auto_router() -> APIRouter:
    router = APIRouter(prefix='/api/gpt-director-auto', tags=['gpt-director-auto'])
    service = GPTDirectorAutoService(ROOT)
    service.recover_interrupted_jobs()

    def fail(exc: GPTDirectorAutoError):
        status = (
            404 if exc.code in {'TASK_NOT_FOUND', 'JOB_NOT_FOUND'}
            else 409 if exc.code in {'TASK_ALREADY_COMPLETED', 'TASK_ALREADY_HAS_RESULT'}
            else 503 if exc.code in {
                'WEBMCP_RELAY_NOT_READY',
                'CHATGPT_CDP_NOT_READY',
                'WEBMCP_DEPENDENCIES_MISSING',
                'CHATGPT_BROWSER_DEPENDENCIES_MISSING',
                'NODE_NOT_FOUND',
                'DIRECTOR_RUNNER_MISSING',
            }
            else 400
        )
        raise HTTPException(status_code=status, detail={'code': exc.code, 'message': str(exc)}) from exc

    @router.get('/status')
    def status():
        return service.status()

    @router.post('/tasks/{task_id}/run')
    def run(task_id: str):
        try:
            return service.create_job(task_id)
        except GPTDirectorAutoError as exc:
            fail(exc)

    @router.get('/jobs/{job_id}')
    def job(job_id: str):
        try:
            return service.get_job(job_id)
        except GPTDirectorAutoError as exc:
            fail(exc)

    return router
