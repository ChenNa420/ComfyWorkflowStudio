from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.db import Database
from backend.workflow.manifest_history import (
    manifest_history,
    manifest_history_version,
    rollback_manifest_version,
)


def manifest_history_router(db: Database) -> APIRouter:
    router = APIRouter(prefix='/api/manifest-history', tags=['manifest-history'])

    @router.get('/{workflow_id}')
    def history(workflow_id: str):
        result = manifest_history(workflow_id)
        if result is None:
            raise HTTPException(status_code=404, detail='workflow_not_found')
        return result

    @router.get('/{workflow_id}/{version_id}')
    def version(workflow_id: str, version_id: str):
        result = manifest_history_version(workflow_id, version_id)
        if result is None:
            raise HTTPException(status_code=404, detail='version_not_found')
        return result

    @router.post('/{workflow_id}/{version_id}/rollback')
    def rollback(workflow_id: str, version_id: str):
        result = rollback_manifest_version(db, workflow_id, version_id)
        if result is None:
            raise HTTPException(status_code=404, detail='workflow_not_found')
        if result.get('error'):
            detail = str(result['error'])
            raise HTTPException(status_code=404 if detail == 'version_not_found' else 409, detail=detail)
        return result

    return router
