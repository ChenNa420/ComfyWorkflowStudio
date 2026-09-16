from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db import Database
from backend.workflow.dependencies import dependency_inventory
from backend.workflow.knowledge import (
    search_workflow_knowledge,
    workflow_knowledge_detail,
    workflow_knowledge_stats,
)


def _dependency_statuses() -> dict[str, str]:
    inventory = dependency_inventory()
    return {
        str(item.get('workflowId')): str(item.get('status') or '')
        for item in inventory.get('workflows') or []
        if item.get('workflowId')
    }


def workflow_knowledge_router(db: Database) -> APIRouter:
    router = APIRouter(prefix='/api/workflow-knowledge', tags=['workflow-knowledge'])

    @router.get('')
    def list_knowledge(
        q: str = Query(default=''),
        category: str | None = Query(default=None),
        capability: str | None = Query(default=None),
        health: str | None = Query(default=None),
        family: str | None = Query(default=None),
        limit: int = Query(default=500, ge=1, le=1000),
    ):
        return search_workflow_knowledge(
            db,
            q=q,
            category=category,
            capability=capability,
            health=health,
            family=family,
            limit=limit,
            dependency_statuses=_dependency_statuses(),
        )

    @router.get('/stats')
    def stats():
        return workflow_knowledge_stats(db, dependency_statuses=_dependency_statuses())

    @router.get('/recommendations')
    def recommendations(
        capability: str | None = Query(default=None),
        q: str = Query(default=''),
        category: str | None = Query(default=None),
        family: str | None = Query(default=None),
        readyOnly: bool = Query(default=True),
        limit: int = Query(default=12, ge=1, le=100),
    ):
        health = 'READY' if readyOnly else None
        items = search_workflow_knowledge(
            db,
            q=q,
            category=category,
            capability=capability,
            health=health,
            family=family,
            limit=limit,
            dependency_statuses=_dependency_statuses(),
        )
        return {
            'items': items,
            'criteria': {
                'capability': capability,
                'query': q,
                'category': category,
                'family': family,
                'readyOnly': readyOnly,
                'dependencyAware': True,
            },
        }

    @router.get('/{workflow_id}')
    def detail(workflow_id: str):
        dependency_status = _dependency_statuses().get(workflow_id)
        item = workflow_knowledge_detail(db, workflow_id, dependency_status=dependency_status)
        if item is None:
            raise HTTPException(status_code=404, detail='workflow_not_found')
        return item

    return router
