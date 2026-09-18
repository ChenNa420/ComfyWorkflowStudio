from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db import Database
from backend.workflow.preflight import preflight_detail, preflight_report


def workflow_preflight_router(db: Database) -> APIRouter:
    router = APIRouter(prefix='/api/preflight', tags=['preflight'])

    @router.get('')
    def report(
        capability: str | None = Query(default=None),
        category: str | None = Query(default=None),
        certifiedOnly: bool = Query(default=False),
        forceRefresh: bool = Query(default=False),
        limit: int = Query(default=500, ge=1, le=1000),
    ):
        return preflight_report(
            db,
            capability=capability,
            category=category,
            certified_only=certifiedOnly,
            force_refresh=forceRefresh,
            limit=limit,
        )

    @router.get('/{workflow_id}')
    def detail(workflow_id: str, forceRefresh: bool = Query(default=False)):
        item = preflight_detail(db, workflow_id, force_refresh=forceRefresh)
        if item is None:
            raise HTTPException(status_code=404, detail='workflow_not_found')
        return item

    return router
