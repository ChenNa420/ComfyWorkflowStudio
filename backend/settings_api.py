from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.comfy.client import ComfyClient, ComfyClientError
from backend.db import DEFAULT_DB, Database
from backend.settings import SettingsUpdate, effective_comfy_url, read_overrides, storage_status, write_overrides
from backend.workflow.knowledge import search_workflow_knowledge


def settings_router(db: Database) -> APIRouter:
    router = APIRouter(prefix='/api/settings', tags=['settings'])

    def workflow_candidates() -> list[dict]:
        # Candidate discovery stays local and fast. Runtime submission still
        # performs the authoritative live CERTIFIED + dependency READY gate.
        cards = search_workflow_knowledge(db, limit=1000, dependency_statuses={})
        return [{
            'workflowId': item['id'],
            'name': item['name'],
            'category': item['category'],
            'capabilities': item.get('capabilities') or [],
            'outputs': [output.get('type') for output in item.get('manifest', {}).get('outputs', [])],
            'health': item['health'],
            'dependencyStatus': item.get('dependencyStatus') or 'UNKNOWN',
        } for item in cards]

    def response() -> dict:
        overrides = read_overrides(db)
        comfy_url, source = effective_comfy_url(db)
        connected, comfy_error = False, None
        try:
            ComfyClient(comfy_url, timeout=3).system_stats()
            connected = True
        except ComfyClientError as exc:
            comfy_error = str(exc)
        return {
            'comfyUi': {
                'url': comfy_url,
                'source': source,
                'connected': connected,
                'error': comfy_error,
                'editable': True,
                'takesEffect': 'immediate',
            },
            'storage': storage_status(),
            'taskPolicy': {
                'maxConcurrency': {'value': 1, 'editable': False},
                'executionMode': {'value': 'serial', 'editable': False},
                'outputTimeout': {'value': 900, 'editable': False, 'scope': 'workflow_manifest'},
                'retryUnknown': {'value': False, 'editable': False},
                'uncertainBehavior': {'value': 'UNKNOWN / NEEDS_REVIEW，等待人工确认', 'editable': False},
                'duplicateSubmissionProtection': {'value': True, 'editable': False},
                'runtimeClone': {'value': True, 'editable': False},
                'preserveOriginalWorkflow': {'value': True, 'editable': False},
            },
            'workflow': {
                'defaultImageWorkflowId': overrides.get('defaultImageWorkflowId'),
                'defaultVideoWorkflowId': overrides.get('defaultVideoWorkflowId'),
                'productionVideoWorkflowId': overrides.get('productionVideoWorkflowId'),
                'showReadyOnly': bool(overrides.get('showReadyOnly', True)),
                'requireCertified': {'value': True, 'editable': False},
                'requireDependencyReady': {'value': True, 'editable': False},
                'candidates': workflow_candidates(),
            },
            'advanced': {
                'phase': '1H',
                'subphase': '1H-7',
                'apiVersion': '0.11.0',
                'databasePath': str(DEFAULT_DB.resolve()),
                'databaseEditable': False,
                'configurationSources': ['local_override', 'environment', 'application_default'],
                'runtimeSafety': 'Strict serial · Runtime Clone · CERTIFIED + dependency READY · UNKNOWN no retry',
            },
            'restartRequired': [],
        }

    @router.get('')
    def get_settings():
        return response()

    @router.put('')
    def update_settings(payload: SettingsUpdate):
        updates = payload.model_dump(exclude_unset=True)
        candidates = {item['workflowId']: item for item in workflow_candidates()}
        for key in ('defaultImageWorkflowId', 'defaultVideoWorkflowId', 'productionVideoWorkflowId'):
            workflow_id = updates.get(key)
            if not workflow_id:
                continue
            candidate = candidates.get(workflow_id)
            if candidate is None:
                raise HTTPException(status_code=422, detail={'code': 'WORKFLOW_NOT_FOUND', 'field': key})
            outputs = {str(value).lower() for value in candidate.get('outputs') or []}
            capabilities = {str(value).lower() for value in candidate.get('capabilities') or []}
            needs_video = key != 'defaultImageWorkflowId'
            compatible = ('video' in outputs or 'video-generation' in capabilities or 'image-to-video' in capabilities) if needs_video else ('image' in outputs or 'image-generation' in capabilities)
            if not compatible:
                raise HTTPException(status_code=422, detail={'code': 'WORKFLOW_TYPE_MISMATCH', 'field': key})
        write_overrides(db, updates)
        result = response()
        result['saved'] = sorted(updates)
        return result

    @router.post('/comfyui/test')
    def test_comfyui(payload: SettingsUpdate):
        url = payload.comfyUiUrl or effective_comfy_url(db)[0]
        try:
            stats = ComfyClient(url, timeout=5).system_stats()
            return {'connected': True, 'url': url, 'systemStatsAvailable': isinstance(stats, dict)}
        except ComfyClientError as exc:
            return {'connected': False, 'url': url, 'error': str(exc)}

    return router
