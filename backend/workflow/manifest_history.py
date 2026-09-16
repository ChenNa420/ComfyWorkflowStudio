from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.db import Database, ROOT
from backend.models import WorkflowManifest
from backend.workflow.manifest import discover_manifests, save_manifest

HISTORY_DIR_NAME = 'manifest-history'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def _manifest_hash(manifest: WorkflowManifest) -> str:
    payload = json.dumps(manifest.model_dump(mode='json'), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def _history_dir(manifest_path: Path) -> Path:
    resolved = manifest_path.resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        # Unit tests and external temporary packages keep history beside the
        # temporary manifest so they never pollute the real repository.
        return manifest_path.parent / HISTORY_DIR_NAME
    # Production history belongs to ignored local storage, never to the
    # third-party Workflow Package or tracked workflows directory.
    return ROOT / 'storage' / HISTORY_DIR_NAME / manifest_path.parent.name


def _snapshot_payload(
    manifest: WorkflowManifest,
    *,
    action: str,
    note: str = '',
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        'schemaVersion': 1,
        'versionId': '',
        'workflowId': manifest.workflowId,
        'createdAt': _now(),
        'action': action,
        'note': note,
        'manifestHash': _manifest_hash(manifest),
        'metadata': metadata or {},
        'manifest': manifest.model_dump(mode='json'),
    }


def record_manifest_version(
    manifest_path: Path,
    manifest: WorkflowManifest,
    *,
    action: str,
    note: str = '',
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    directory = _history_dir(manifest_path)
    directory.mkdir(parents=True, exist_ok=True)
    payload = _snapshot_payload(manifest, action=action, note=note, metadata=metadata)
    base_id = f"{_stamp()}-{payload['manifestHash'][:10]}"
    version_id = base_id
    target = directory / f'{version_id}.json'
    counter = 1
    while target.exists():
        version_id = f'{base_id}-{counter}'
        target = directory / f'{version_id}.json'
        counter += 1
    payload['versionId'] = version_id
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {key: value for key, value in payload.items() if key != 'manifest'}


def ensure_manifest_baseline(manifest_path: Path, manifest: WorkflowManifest) -> dict[str, Any] | None:
    directory = _history_dir(manifest_path)
    if directory.is_dir() and any(directory.glob('*.json')):
        return None
    return record_manifest_version(
        manifest_path,
        manifest,
        action='baseline',
        note='首次建立 Manifest 版本历史。',
    )


def list_manifest_versions(manifest_path: Path) -> list[dict[str, Any]]:
    directory = _history_dir(manifest_path)
    if not directory.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in directory.glob('*.json'):
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        items.append({
            'versionId': payload.get('versionId') or path.stem,
            'workflowId': payload.get('workflowId'),
            'createdAt': payload.get('createdAt'),
            'action': payload.get('action') or 'snapshot',
            'note': payload.get('note') or '',
            'manifestHash': payload.get('manifestHash'),
            'metadata': payload.get('metadata') or {},
        })
    items.sort(key=lambda item: str(item.get('createdAt') or ''), reverse=True)
    return items


def load_manifest_version(manifest_path: Path, version_id: str) -> dict[str, Any] | None:
    safe_id = Path(version_id).name
    if safe_id != version_id or not safe_id:
        return None
    target = _history_dir(manifest_path) / f'{safe_id}.json'
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _update_db_manifest(db: Database, manifest: WorkflowManifest) -> None:
    with db.connect() as conn:
        conn.execute(
            """
            UPDATE workflows
            SET name=?, category=?, description=?, difficulty=?, manifest_json=?, updated_at=datetime('now')
            WHERE id=?
            """,
            (
                manifest.name,
                manifest.category,
                manifest.description,
                manifest.difficulty,
                json.dumps(manifest.model_dump(mode='json'), ensure_ascii=False),
                manifest.workflowId,
            ),
        )


def save_manifest_with_history(
    db: Database,
    manifest_path: Path,
    current: WorkflowManifest,
    updated: WorkflowManifest,
    *,
    action: str,
    note: str = '',
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_manifest_baseline(manifest_path, current)
    before = record_manifest_version(
        manifest_path,
        current,
        action=f'{action}:before',
        note=note,
        metadata=metadata,
    )
    save_manifest(updated, manifest_path)
    _update_db_manifest(db, updated)
    after = record_manifest_version(
        manifest_path,
        updated,
        action=action,
        note=note,
        metadata=metadata,
    )
    return {'before': before, 'after': after}


def _find_manifest(workflow_id: str) -> tuple[Path, WorkflowManifest] | None:
    for path, manifest in discover_manifests():
        if manifest.workflowId == workflow_id:
            return path, manifest
    return None


def manifest_history(workflow_id: str) -> dict[str, Any] | None:
    found = _find_manifest(workflow_id)
    if found is None:
        return None
    path, manifest = found
    return {
        'workflowId': workflow_id,
        'currentHash': _manifest_hash(manifest),
        'versions': list_manifest_versions(path),
    }


def manifest_history_version(workflow_id: str, version_id: str) -> dict[str, Any] | None:
    found = _find_manifest(workflow_id)
    if found is None:
        return None
    path, _ = found
    return load_manifest_version(path, version_id)


def rollback_manifest_version(db: Database, workflow_id: str, version_id: str) -> dict[str, Any] | None:
    found = _find_manifest(workflow_id)
    if found is None:
        return None
    path, current = found
    ensure_manifest_baseline(path, current)
    snapshot = load_manifest_version(path, version_id)
    if snapshot is None or not isinstance(snapshot.get('manifest'), dict):
        return {'workflowId': workflow_id, 'error': 'version_not_found'}
    target = WorkflowManifest.model_validate(snapshot['manifest'])
    if target.workflowId != workflow_id:
        return {'workflowId': workflow_id, 'error': 'workflow_id_mismatch'}
    versions = save_manifest_with_history(
        db,
        path,
        current,
        target,
        action='rollback',
        note=f'回滚到 {version_id}',
        metadata={'sourceVersionId': version_id},
    )
    return {
        'workflowId': workflow_id,
        'rolledBackTo': version_id,
        'manifest': target.model_dump(mode='json'),
        'versions': versions,
    }
