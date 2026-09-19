from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.bindings import bindings_router
from backend.comic_story_api import comic_story_router
from backend.gpt_image_api import gpt_image_router
from backend.gpt_director_auto_api import gpt_director_auto_router
from backend.comfy.client import ComfyClient, ComfyClientError, comfy_url_from_env
from backend.db import Database, ROOT
from backend.models import GenerationTaskCreate, WorkflowManifest
from backend.settings_api import settings_router
from backend.workflow.catalog import import_payload
from backend.workflow.dependencies import execution_node_types
from backend.workflow.dependencies_api import workflow_dependencies_router
from backend.workflow.knowledge_api import workflow_knowledge_router
from backend.workflow.manifest import discover_manifests
from backend.workflow.manifest_history import save_manifest_with_history
from backend.workflow.manifest_history_api import manifest_history_router
from backend.workflow.manifest_review_api import manifest_review_router
from backend.workflow.readiness_api import workflow_readiness_router
from backend.workflow.remediation_guides_api import remediation_guides_router
from backend.workflow.pilot_api import workflow_pilot_router
from backend.workflow.runs_api import workflow_runs_router


def create_app() -> FastAPI:
    db = Database()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.initialize()
        app.state.db = db
        yield

    app = FastAPI(title='ComfyWorkflowStudio API', version='0.11.0', lifespan=lifespan)

    @app.get('/api/health')
    def health():
        manifests = discover_manifests()
        comfy_status = 'offline'
        try:
            ComfyClient(comfy_url_from_env(), timeout=3).system_stats()
            comfy_status = 'connected'
        except ComfyClientError:
            pass
        with db.connect() as conn:
            running = conn.execute("SELECT COUNT(*) AS c FROM generation_tasks WHERE status IN ('WAITING','PREPARING','SUBMITTING','QUEUED','RUNNING')").fetchone()['c']
            outputs = conn.execute('SELECT COUNT(*) AS c FROM outputs').fetchone()['c']
            materials = conn.execute('SELECT COUNT(*) AS c FROM materials').fetchone()['c']
        return {
            'status': 'ok',
            'service': 'ComfyWorkflowStudio',
            'phase': '1H',
            'subphase': '1H-4',
            'workflowPackages': len(manifests),
            'runningTasks': running,
            'outputs': outputs,
            'materials': materials,
            'comfyUi': comfy_status,
            'comfyUiUrl': comfy_url_from_env(),
        }

    @app.get('/api/comfy/status')
    def comfy_status():
        client = ComfyClient(comfy_url_from_env(), timeout=5)
        try:
            stats = client.system_stats()
            queue = client.queue()
        except ComfyClientError as exc:
            return {'connected': False, 'url': comfy_url_from_env(), 'error': str(exc)}
        return {'connected': True, 'url': comfy_url_from_env(), 'stats': stats, 'queue': queue}

    @app.get('/api/workflows')
    def list_workflows(capability: str | None = None):
        result = []
        for path, manifest in discover_manifests():
            if capability and capability not in manifest.capabilities:
                continue
            analysis_path = path.parent / 'analysis.json'
            analysis = {}
            if analysis_path.is_file():
                try:
                    analysis = json.loads(analysis_path.read_text(encoding='utf-8'))
                except (OSError, json.JSONDecodeError):
                    analysis = {}
            result.append({
                'id': manifest.workflowId,
                'name': manifest.name,
                'category': manifest.category,
                'description': manifest.description,
                'difficulty': manifest.difficulty,
                'capabilities': manifest.capabilities,
                'inputs': len(manifest.inputs),
                'outputs': [item.type for item in manifest.outputs],
                'source': manifest.source.model_dump(),
                'format': analysis.get('format'),
                'nodeCount': analysis.get('nodeCount'),
                'contentHash': analysis.get('hash'),
            })
        return result

    @app.get('/api/workflows/{workflow_id}/manifest')
    def workflow_manifest(workflow_id: str):
        for _, manifest in discover_manifests():
            if manifest.workflowId == workflow_id:
                return manifest.model_dump(mode='json')
        raise HTTPException(status_code=404, detail='workflow_not_found')

    @app.put('/api/workflows/{workflow_id}/manifest')
    def update_workflow_manifest(workflow_id: str, payload: WorkflowManifest):
        if payload.workflowId != workflow_id:
            raise HTTPException(status_code=400, detail='workflow_id_mismatch')
        for path, current in discover_manifests():
            if path.parent.name == workflow_id or current.workflowId == workflow_id:
                versions = save_manifest_with_history(
                    db,
                    path,
                    current,
                    payload,
                    action='manual-update',
                    note='通过 Workflow Manifest API 更新。',
                )
                return {'ok': True, 'workflowId': workflow_id, 'versions': versions}
        raise HTTPException(status_code=404, detail='workflow_not_found')

    @app.get('/api/workflows/{workflow_id}/analysis')
    def workflow_analysis(workflow_id: str):
        for path, manifest in discover_manifests():
            if manifest.workflowId != workflow_id:
                continue
            analysis_path = path.parent / 'analysis.json'
            if not analysis_path.is_file():
                return {'workflowId': workflow_id, 'analysis': None}
            return json.loads(analysis_path.read_text(encoding='utf-8'))
        raise HTTPException(status_code=404, detail='workflow_not_found')

    @app.get('/api/workflows/{workflow_id}/compatibility')
    def workflow_compatibility(workflow_id: str):
        for path, manifest in discover_manifests():
            if manifest.workflowId != workflow_id:
                continue
            analysis_path = path.parent / 'analysis.json'
            analysis = {}
            if analysis_path.is_file():
                try:
                    value = json.loads(analysis_path.read_text(encoding='utf-8'))
                    analysis = value if isinstance(value, dict) else {}
                except (OSError, json.JSONDecodeError):
                    analysis = {}
            try:
                object_info = ComfyClient(comfy_url_from_env(), timeout=10).object_info()
            except ComfyClientError as exc:
                return {'workflowId': workflow_id, 'status': 'COMFY_OFFLINE', 'missingNodes': [], 'ignoredNodeTypes': [], 'error': str(exc)}
            node_types, ignored = execution_node_types(path, analysis, connected=True, object_info=object_info)
            missing = [node_type for node_type in node_types if node_type not in object_info]
            return {
                'workflowId': workflow_id,
                'status': 'READY' if not missing else 'MISSING_NODES',
                'missingNodes': missing,
                'ignoredNodeTypes': ignored,
                'checkedNodeTypes': len(node_types),
            }
        raise HTTPException(status_code=404, detail='workflow_not_found')

    @app.post('/api/workflows/import')
    async def import_workflows(files: list[UploadFile] = File(...)):
        results = []
        for upload in files:
            raw = await upload.read()
            results.append(import_payload(upload.filename or 'upload.json', raw, db, source_name='Local Import'))
        return {
            'ok': all(item.get('ok') for item in results),
            'files': results,
            'summary': {
                'imported': sum(len(item.get('imported') or []) for item in results),
                'duplicates': sum(len(item.get('duplicates') or []) for item in results),
                'resources': sum(len(item.get('resources') or []) for item in results),
                'invalid': sum(int(item.get('invalid') or 0) for item in results),
            },
        }

    @app.post('/api/materials')
    async def upload_material(file: UploadFile = File(...), material_type: str | None = None):
        limit = max(1, int(os.getenv('CWS_MAX_MATERIAL_MB', '100'))) * 1024 * 1024
        chunks, total = [], 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk: break
            total += len(chunk)
            if total > limit: raise HTTPException(status_code=413, detail='MATERIAL_TOO_LARGE')
            chunks.append(chunk)
        raw = b''.join(chunks)
        if not raw:
            raise HTTPException(status_code=400, detail='empty_file')
        filename = Path(file.filename or 'material.bin').name
        suffix = Path(filename).suffix
        material_id = f'mat-{uuid.uuid4().hex[:12]}'
        storage_dir = ROOT / 'storage' / 'materials'
        storage_dir.mkdir(parents=True, exist_ok=True)
        target = storage_dir / f'{material_id}{suffix}'
        target.write_bytes(raw)
        detected_type = material_type or _material_type_from_content(file.content_type or '', suffix)
        with db.connect() as conn:
            conn.execute(
                'INSERT INTO materials(id,type,name,file_path,thumbnail_path,width,height,duration,tags_json,source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,datetime(\'now\'))',
                (material_id, detected_type, filename, str(target), None, None, None, None, '[]', 'upload'),
            )
        return {'id': material_id, 'type': detected_type, 'name': filename, 'filePath': str(target)}

    @app.get('/api/materials')
    def list_materials(limit: int = 200):
        limit = max(1, min(limit, 1000))
        with db.connect() as conn:
            rows = conn.execute('SELECT * FROM materials ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
        return [dict(row) for row in rows]

    @app.post('/api/tasks')
    def create_task(payload: GenerationTaskCreate):
        del payload
        raise HTTPException(status_code=410, detail={'code': 'LEGACY_TASK_API_DISABLED', 'message': 'Use /api/workflows/{id}/runs'})

    @app.get('/api/tasks')
    def list_tasks(limit: int = 100):
        limit = max(1, min(limit, 500))
        with db.connect() as conn:
            rows = conn.execute('SELECT * FROM generation_tasks ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
        return [dict(row) for row in rows]

    @app.get('/api/tasks/{task_id}')
    def task_detail(task_id: str):
        with db.connect() as conn:
            row = conn.execute('SELECT * FROM generation_tasks WHERE id=?', (task_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail='task_not_found')
            outputs = conn.execute('SELECT * FROM outputs WHERE task_id=? ORDER BY created_at', (task_id,)).fetchall()
        data = dict(row)
        data['outputs'] = [dict(item) for item in outputs]
        return data

    @app.get('/api/tasks/{task_id}/events')
    def task_events(task_id: str):
        with db.connect() as conn:
            exists = conn.execute('SELECT 1 FROM generation_tasks WHERE id=?', (task_id,)).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail='task_not_found')
            rows = conn.execute('SELECT * FROM generation_task_events WHERE task_id=? ORDER BY id', (task_id,)).fetchall()
        return [dict(row) for row in rows]

    @app.get('/api/outputs')
    def list_outputs(
        page: int = 1,
        page_size: int = 8,
        type: str = 'all',
        project_id: str | None = None,
        time_filter: str = 'all',
        sort: str = 'newest',
    ):
        page = max(1, page)
        if page_size not in {8, 12, 16}:
            raise HTTPException(status_code=400, detail='invalid_page_size')
        if type not in {'all', 'image', 'video', 'audio'}:
            raise HTTPException(status_code=400, detail='invalid_output_type')
        if time_filter not in {'all', 'today', 'week', 'month'}:
            raise HTTPException(status_code=400, detail='invalid_time_filter')
        if sort not in {'newest', 'oldest'}:
            raise HTTPException(status_code=400, detail='invalid_sort')

        project_key = "COALESCE(NULLIF(t.episode_id,''), NULLIF(t.project_id,''), o.workflow_id)"
        base_where: list[str] = []
        base_params: list[object] = []

        if project_id and project_id != 'all':
            base_where.append(f'{project_key} = ?')
            base_params.append(project_id)

        if time_filter != 'all':
            age_map = {
                'today': '-1 day',
                'week': '-7 days',
                'month': '-30 days',
            }
            base_where.append("datetime(o.created_at) >= datetime('now', ?)")
            base_params.append(age_map[time_filter])

        item_where = list(base_where)
        item_params = list(base_params)
        if type != 'all':
            item_where.append('o.type = ?')
            item_params.append(type)

        base_clause = (' WHERE ' + ' AND '.join(base_where)) if base_where else ''
        item_clause = (' WHERE ' + ' AND '.join(item_where)) if item_where else ''
        order = 'DESC' if sort == 'newest' else 'ASC'

        with db.connect() as conn:
            total = conn.execute(
                f'''
                SELECT COUNT(*) AS c
                FROM outputs o
                LEFT JOIN generation_tasks t ON t.id = o.task_id
                {item_clause}
                ''',
                tuple(item_params),
            ).fetchone()['c']

            total_pages = (total + page_size - 1) // page_size if total else 0
            if total_pages and page > total_pages:
                page = total_pages
            offset = (page - 1) * page_size

            rows = conn.execute(
                f'''
                SELECT o.*,
                       w.name AS workflow_name,
                       t.project_id,
                       t.episode_id,
                       t.shot_id
                FROM outputs o
                LEFT JOIN workflows w ON w.id = o.workflow_id
                LEFT JOIN generation_tasks t ON t.id = o.task_id
                {item_clause}
                ORDER BY o.created_at {order}
                LIMIT ? OFFSET ?
                ''',
                tuple(item_params + [page_size, offset]),
            ).fetchall()

            count_rows = conn.execute(
                f'''
                SELECT o.type, COUNT(*) AS c
                FROM outputs o
                LEFT JOIN generation_tasks t ON t.id = o.task_id
                {base_clause}
                GROUP BY o.type
                ''',
                tuple(base_params),
            ).fetchall()

            project_rows = conn.execute(
                f'''
                SELECT DISTINCT
                       {project_key} AS id,
                       COALESCE(
                           NULLIF(t.episode_id,''),
                           NULLIF(t.project_id,''),
                           NULLIF(w.name,''),
                           o.workflow_id
                       ) AS label
                FROM outputs o
                LEFT JOIN workflows w ON w.id = o.workflow_id
                LEFT JOIN generation_tasks t ON t.id = o.task_id
                WHERE {project_key} IS NOT NULL
                ORDER BY label COLLATE NOCASE
                '''
            ).fetchall()

        counts = {'all': 0, 'image': 0, 'video': 0, 'audio': 0}
        for row in count_rows:
            row_type = str(row['type'])
            count = int(row['c'])
            counts['all'] += count
            if row_type in counts:
                counts[row_type] = count

        return {
            'items': [dict(row) for row in rows],
            'page': page,
            'page_size': page_size,
            'total': int(total),
            'total_pages': int(total_pages),
            'counts': counts,
            'projects': [dict(row) for row in project_rows],
        }

    @app.get('/api/outputs/{output_id}/file')
    def output_file(output_id: str, download: bool = False):
        with db.connect() as conn:
            row = conn.execute('SELECT * FROM outputs WHERE id=?', (output_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail='output_not_found')
        path = Path(row['file_path']).resolve()
        try:
            path.relative_to((ROOT / 'storage' / 'outputs').resolve())
        except ValueError as exc:
            raise HTTPException(status_code=403, detail='output_path_outside_storage') from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail='output_file_missing')
        return FileResponse(path, filename=path.name if download else None, content_disposition_type='attachment' if download else 'inline')

    app.include_router(comic_story_router())
    app.include_router(gpt_image_router())
    app.include_router(gpt_director_auto_router())
    app.include_router(workflow_knowledge_router(db))
    app.include_router(workflow_dependencies_router())
    app.include_router(manifest_review_router(db))
    app.include_router(manifest_history_router(db))
    app.include_router(workflow_readiness_router(db))
    app.include_router(remediation_guides_router())
    app.include_router(workflow_pilot_router(db))
    app.include_router(workflow_runs_router(db))
    app.include_router(bindings_router(db))
    app.include_router(settings_router(db))
    return app


def _material_type_from_content(content_type: str, suffix: str) -> str:
    if content_type.startswith('image/'):
        return 'image'
    if content_type.startswith('video/'):
        return 'video'
    if content_type.startswith('audio/'):
        return 'audio'
    lowered = suffix.lower()
    if lowered in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
        return 'image'
    if lowered in {'.mp4', '.mov', '.webm', '.mkv'}:
        return 'video'
    if lowered in {'.wav', '.mp3', '.flac', '.m4a'}:
        return 'audio'
    return 'file'


app = create_app()
