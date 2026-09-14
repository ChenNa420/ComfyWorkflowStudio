from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.db import Database
from backend.workflow.manifest import discover_manifests


def create_app() -> FastAPI:
    db = Database()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.initialize()
        app.state.db = db
        yield

    app = FastAPI(title='ComfyWorkflowStudio API', version='0.1.0', lifespan=lifespan)

    @app.get('/api/health')
    def health():
        manifests = discover_manifests()
        return {
            'status': 'ok',
            'service': 'ComfyWorkflowStudio',
            'phase': '1A',
            'workflowPackages': len(manifests),
            'comfyUi': 'not-configured',
        }

    @app.get('/api/workflows')
    def list_workflows():
        return [
            {
                'id': manifest.workflowId,
                'name': manifest.name,
                'category': manifest.category,
                'description': manifest.description,
                'difficulty': manifest.difficulty,
                'capabilities': manifest.capabilities,
                'inputs': len(manifest.inputs),
                'outputs': [item.type for item in manifest.outputs],
                'source': manifest.source.model_dump(),
            }
            for _, manifest in discover_manifests()
        ]

    @app.get('/api/workflows/{workflow_id}/manifest')
    def workflow_manifest(workflow_id: str):
        for _, manifest in discover_manifests():
            if manifest.workflowId == workflow_id:
                return manifest.model_dump(mode='json')
        return {'error': 'workflow_not_found', 'workflowId': workflow_id}

    return app


app = create_app()
