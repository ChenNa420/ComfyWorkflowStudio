from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.db import Database
from backend.models import WorkflowBindingCreate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_scope(scope_type: str, scope_id: str | None) -> str | None:
    if scope_type == 'SYSTEM':
        return None
    value = (scope_id or '').strip()
    if not value:
        raise HTTPException(status_code=422, detail=f'{scope_type} binding requires scopeId')
    return value


def _workflow_payload(row: Any) -> dict[str, Any]:
    manifest = json.loads(row['manifest_json'] or '{}')
    return {
        'id': row['id'],
        'name': row['name'],
        'category': row['category'],
        'description': row['description'] or '',
        'difficulty': row['difficulty'],
        'capabilities': manifest.get('capabilities') or [],
        'inputs': manifest.get('inputs') or [],
        'parameters': manifest.get('parameters') or [],
        'outputs': manifest.get('outputs') or [],
        'runtime': manifest.get('runtime') or {},
    }


def _validate_workflow(conn, workflow_id: str, capability: str):
    row = conn.execute('SELECT * FROM workflows WHERE id=? AND enabled=1', (workflow_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail='workflow_not_found')
    manifest = json.loads(row['manifest_json'] or '{}')
    capabilities = set(manifest.get('capabilities') or [])
    if capability not in capabilities:
        raise HTTPException(status_code=422, detail='workflow_capability_mismatch')
    return row


def upsert_binding(db: Database, payload: WorkflowBindingCreate) -> dict[str, Any]:
    scope_id = _normalize_scope(payload.scopeType, payload.scopeId)
    now = _now()
    with db.connect() as conn:
        _validate_workflow(conn, payload.workflowId, payload.capability)
        existing = conn.execute(
            """
            SELECT * FROM workflow_bindings
            WHERE client_app=? AND capability=? AND scope_type=?
              AND COALESCE(scope_id,'')=COALESCE(?, '')
            """,
            (payload.clientApp, payload.capability, payload.scopeType, scope_id),
        ).fetchone()
        preset_json = json.dumps(payload.preset, ensure_ascii=False)
        if existing:
            binding_id = existing['id']
            conn.execute(
                """
                UPDATE workflow_bindings
                SET workflow_id=?, preset_json=?, enabled=1, updated_at=?
                WHERE id=?
                """,
                (payload.workflowId, preset_json, now, binding_id),
            )
        else:
            binding_id = f'bind-{uuid.uuid4().hex[:12]}'
            conn.execute(
                """
                INSERT INTO workflow_bindings(
                    id, client_app, capability, scope_type, scope_id,
                    workflow_id, preset_json, enabled, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    binding_id,
                    payload.clientApp,
                    payload.capability,
                    payload.scopeType,
                    scope_id,
                    payload.workflowId,
                    preset_json,
                    1,
                    now,
                    now,
                ),
            )
        row = conn.execute('SELECT * FROM workflow_bindings WHERE id=?', (binding_id,)).fetchone()
        workflow = conn.execute('SELECT * FROM workflows WHERE id=?', (payload.workflowId,)).fetchone()
    return {
        'id': row['id'],
        'clientApp': row['client_app'],
        'capability': row['capability'],
        'scopeType': row['scope_type'],
        'scopeId': row['scope_id'],
        'workflowId': row['workflow_id'],
        'preset': json.loads(row['preset_json'] or '{}'),
        'workflow': _workflow_payload(workflow),
    }


def resolve_binding(
    db: Database,
    *,
    client_app: str,
    capability: str,
    episode_id: str | None = None,
    shot_id: str | None = None,
) -> dict[str, Any]:
    candidates: list[tuple[str, str | None]] = []
    if shot_id:
        candidates.append(('SHOT', shot_id))
    if episode_id:
        candidates.append(('EPISODE', episode_id))
    candidates.append(('SYSTEM', None))

    with db.connect() as conn:
        for scope_type, scope_id in candidates:
            row = conn.execute(
                """
                SELECT * FROM workflow_bindings
                WHERE client_app=? AND capability=? AND scope_type=?
                  AND COALESCE(scope_id,'')=COALESCE(?, '')
                  AND enabled=1
                """,
                (client_app, capability, scope_type, scope_id),
            ).fetchone()
            if row is None:
                continue
            workflow = conn.execute('SELECT * FROM workflows WHERE id=? AND enabled=1', (row['workflow_id'],)).fetchone()
            if workflow is None:
                continue
            return {
                'resolved': True,
                'source': scope_type,
                'bindingId': row['id'],
                'workflowId': row['workflow_id'],
                'scopeId': row['scope_id'],
                'preset': json.loads(row['preset_json'] or '{}'),
                'workflow': _workflow_payload(workflow),
            }
    return {
        'resolved': False,
        'source': None,
        'bindingId': None,
        'workflowId': None,
        'scopeId': None,
        'preset': {},
        'workflow': None,
    }


def bindings_router(db: Database) -> APIRouter:
    router = APIRouter(prefix='/api/bindings', tags=['workflow-bindings'])

    @router.get('')
    def list_bindings(
        clientApp: str | None = Query(default=None),
        capability: str | None = Query(default=None),
    ):
        clauses = ['enabled=1']
        values: list[Any] = []
        if clientApp:
            clauses.append('client_app=?')
            values.append(clientApp)
        if capability:
            clauses.append('capability=?')
            values.append(capability)
        sql = 'SELECT * FROM workflow_bindings WHERE ' + ' AND '.join(clauses) + ' ORDER BY client_app, capability, scope_type, scope_id'
        with db.connect() as conn:
            rows = conn.execute(sql, values).fetchall()
        return [
            {
                'id': row['id'],
                'clientApp': row['client_app'],
                'capability': row['capability'],
                'scopeType': row['scope_type'],
                'scopeId': row['scope_id'],
                'workflowId': row['workflow_id'],
                'preset': json.loads(row['preset_json'] or '{}'),
            }
            for row in rows
        ]

    @router.put('')
    def put_binding(payload: WorkflowBindingCreate):
        return upsert_binding(db, payload)

    @router.get('/resolve')
    def get_resolved_binding(
        clientApp: str,
        capability: str,
        episodeId: str | None = None,
        shotId: str | None = None,
    ):
        return resolve_binding(
            db,
            client_app=clientApp,
            capability=capability,
            episode_id=episodeId,
            shot_id=shotId,
        )

    @router.delete('/{binding_id}')
    def delete_binding(binding_id: str):
        with db.connect() as conn:
            row = conn.execute('SELECT id FROM workflow_bindings WHERE id=?', (binding_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail='binding_not_found')
            conn.execute('UPDATE workflow_bindings SET enabled=0, updated_at=? WHERE id=?', (_now(), binding_id))
        return {'ok': True, 'bindingId': binding_id}

    return router
