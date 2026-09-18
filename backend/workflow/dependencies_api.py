from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.workflow.dependencies import dependency_inventory, dependency_workflow


def workflow_dependencies_router() -> APIRouter:
    router = APIRouter(prefix='/api/dependencies', tags=['workflow-dependencies'])

    @router.get('/inventory')
    def inventory(forceRefresh: bool = Query(default=False)):
        return dependency_inventory(force_refresh=forceRefresh)

    @router.get('/summary')
    def summary(forceRefresh: bool = Query(default=False)):
        inventory = dependency_inventory(force_refresh=forceRefresh)
        return {
            'connected': inventory['connected'],
            'comfyUiUrl': inventory['comfyUiUrl'],
            'error': inventory['error'],
            'summary': inventory['summary'],
        }

    @router.get('/workflows')
    def workflows(
        status: str | None = Query(default=None),
        q: str = Query(default=''),
        limit: int = Query(default=500, ge=1, le=1000),
    ):
        inventory = dependency_inventory()
        query = q.strip().casefold()
        items = []
        for item in inventory['workflows']:
            if status and item['status'] != status:
                continue
            if query and query not in f"{item['name']} {item['category']} {' '.join(item['capabilities'])}".casefold():
                continue
            items.append(item)
        return {
            'connected': inventory['connected'],
            'comfyUiUrl': inventory['comfyUiUrl'],
            'error': inventory['error'],
            'items': items[:limit],
        }

    @router.get('/workflows/{workflow_id}')
    def workflow_detail(workflow_id: str):
        inventory = dependency_inventory()
        item = dependency_workflow(inventory, workflow_id)
        if item is None:
            raise HTTPException(status_code=404, detail='workflow_not_found')
        return {
            'connected': inventory['connected'],
            'comfyUiUrl': inventory['comfyUiUrl'],
            'error': inventory['error'],
            'workflow': item,
        }

    @router.get('/models')
    def models(
        status: str | None = Query(default=None),
        modelType: str | None = Query(default=None),
        q: str = Query(default=''),
        limit: int = Query(default=1000, ge=1, le=5000),
    ):
        inventory = dependency_inventory()
        query = q.strip().casefold()
        items = []
        for item in inventory['models']:
            if status and item['status'] != status:
                continue
            if modelType and modelType not in (item.get('modelTypes') or [item.get('modelType')]):
                continue
            if query and query not in f"{item['name']} {item.get('modelType') or ''}".casefold():
                continue
            items.append(item)
        return {
            'connected': inventory['connected'],
            'error': inventory['error'],
            'modelTypes': inventory['summary'].get('modelTypes') or [],
            'items': items[:limit],
        }

    @router.get('/nodes')
    def nodes(
        status: str | None = Query(default=None),
        q: str = Query(default=''),
        limit: int = Query(default=2000, ge=1, le=5000),
    ):
        inventory = dependency_inventory()
        query = q.strip().casefold()
        items = []
        for item in inventory['nodeTypes']:
            if status and item['status'] != status:
                continue
            if query and query not in item['nodeType'].casefold():
                continue
            items.append(item)
        return {'connected': inventory['connected'], 'error': inventory['error'], 'items': items[:limit]}

    return router
