from __future__ import annotations

from fastapi import APIRouter, Query

from backend.workflow.remediation_guides import remediation_guides


def remediation_guides_router() -> APIRouter:
    router = APIRouter(prefix='/api/remediation-guides', tags=['readiness-remediation-guides'])

    @router.get('')
    def list_guides(
        capability: str | None = Query(default=None),
        category: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
        forceRefresh: bool = Query(default=False),
    ):
        return remediation_guides(
            capability=capability,
            category=category,
            limit=limit,
            force_refresh=forceRefresh,
        )

    return router
