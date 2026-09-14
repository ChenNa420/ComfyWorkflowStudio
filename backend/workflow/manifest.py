from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from backend.models import WorkflowManifest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = ROOT / 'workflows'
LOCAL_WORKFLOW_ROOT = ROOT / 'storage' / 'workflow-packages'


def load_manifest(path: str | Path) -> WorkflowManifest:
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    return WorkflowManifest.model_validate(data)


def save_manifest(manifest: WorkflowManifest, path: str | Path) -> None:
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode='json'), ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )


def discover_manifests(root: Path | None = None) -> list[tuple[Path, WorkflowManifest]]:
    bases = [root] if root is not None else [WORKFLOW_ROOT, LOCAL_WORKFLOW_ROOT]
    result: list[tuple[Path, WorkflowManifest]] = []
    for base in bases:
        if base is None or not base.exists():
            continue
        for path in sorted(base.glob('*/manifest.json')):
            try:
                result.append((path, load_manifest(path)))
            except (OSError, json.JSONDecodeError, ValidationError):
                continue
    return result
