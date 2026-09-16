from __future__ import annotations

from fastapi import APIRouter, Query

from backend.workflow.readiness import readiness_plan


def workflow_readiness_router() -> APIRouter:
    router = APIRouter(prefix='/api/readiness', tags=['workflow-readiness'])

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

    return router
