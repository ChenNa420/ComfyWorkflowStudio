from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db import Database
from backend.workflow.manifest_review import apply_safe_manifest_review, manifest_review_queue


def manifest_review_router(db: Database) -> APIRouter:
    router = APIRouter(prefix='/api/manifest-review', tags=['manifest-review'])

    @router.get('')
    def list_reviews(
        needsProposal: bool | None = Query(default=None),
        maxScore: int | None = Query(default=None, ge=0, le=100),
        limit: int = Query(default=500, ge=1, le=1000),
    ):
        items = manifest_review_queue()
        if needsProposal is not None:
            items = [item for item in items if (item['proposalCount'] > 0) == needsProposal]
        if maxScore is not None:
            items = [item for item in items if item['completeness']['score'] <= maxScore]
        return items[:limit]

    @router.get('/{workflow_id}')
    def review_detail(workflow_id: str):
        item = next((item for item in manifest_review_queue() if item['workflowId'] == workflow_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail='workflow_not_found')
        return item

    @router.post('/{workflow_id}/apply-safe')
    def apply_safe(workflow_id: str):
        result = apply_safe_manifest_review(db, workflow_id)
        if result is None:
            raise HTTPException(status_code=404, detail='workflow_not_found')
        return result

    return router
