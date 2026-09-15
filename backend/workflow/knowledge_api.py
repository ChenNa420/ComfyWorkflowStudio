from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db import Database
from backend.workflow.knowledge import (
    search_workflow_knowledge,
    workflow_knowledge_detail,
    workflow_knowledge_stats,
)


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
        )

    @router.get('/stats')
    def stats():
        return workflow_knowledge_stats(db)

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
        )
        return {
            'items': items,
            'criteria': {
                'capability': capability,
                'query': q,
                'category': category,
                'family': family,
                'readyOnly': readyOnly,
            },
        }

    @router.get('/{workflow_id}')
    def detail(workflow_id: str):
        item = workflow_knowledge_detail(db, workflow_id)
        if item is None:
            raise HTTPException(status_code=404, detail='workflow_not_found')
        return item

    return router
