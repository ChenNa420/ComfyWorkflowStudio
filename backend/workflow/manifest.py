from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from backend.models import WorkflowManifest

WORKFLOW_ROOT = Path(__file__).resolve().parents[2] / 'workflows'


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
    base = root or WORKFLOW_ROOT
    if not base.exists():
        return []
    result: list[tuple[Path, WorkflowManifest]] = []
    for path in sorted(base.glob('*/manifest.json')):
        try:
            result.append((path, load_manifest(path)))
        except (OSError, json.JSONDecodeError, ValidationError):
            continue
    return result
