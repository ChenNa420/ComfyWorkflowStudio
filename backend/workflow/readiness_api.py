from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db import Database
from backend.workflow.preflight import preflight_detail, preflight_report
from backend.workflow.readiness import readiness_plan


def workflow_readiness_router(db: Database | None = None) -> APIRouter:
    router = APIRouter(prefix='/api/readiness', tags=['workflow-readiness'])
    database = db or Database()

    @router.get('/plan')
    def plan(
        capability: str | None = Query(default=None),
        category: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        forceRefresh: bool = Query(default=False),
    ):
        return readiness_plan(
            capability=capability,
            category=category,
            limit=limit,
            force_refresh=forceRefresh,
        )

    @router.get('/near-ready')
    def near_ready(
        capability: str | None = Query(default=None),
        category: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ):
        payload = readiness_plan(capability=capability, category=category, limit=limit)
        return {
            'connected': payload['connected'],
            'filters': payload['filters'],
            'summary': payload['summary'],
            'items': payload['nearReadyWorkflows'],
        }

    @router.get('/preflight')
    def preflight(
        capability: str | None = Query(default=None),
        category: str | None = Query(default=None),
        certifiedOnly: bool = Query(default=False),
        forceRefresh: bool = Query(default=False),
        limit: int = Query(default=500, ge=1, le=1000),
    ):
        return preflight_report(
            database,
            capability=capability,
            category=category,
            certified_only=certifiedOnly,
            force_refresh=forceRefresh,
            limit=limit,
        )

    @router.get('/preflight/{workflow_id}')
    def preflight_workflow(workflow_id: str, forceRefresh: bool = Query(default=False)):
        item = preflight_detail(database, workflow_id, force_refresh=forceRefresh)
        if item is None:
            raise HTTPException(status_code=404, detail='workflow_not_found')
        return item

    return router
