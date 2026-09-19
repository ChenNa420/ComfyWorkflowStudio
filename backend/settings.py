from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.db import DEFAULT_DB, ROOT, Database


SETTING_KEYS = {
    'comfyUiUrl',
    'defaultImageWorkflowId',
    'defaultVideoWorkflowId',
    'productionVideoWorkflowId',
    'showReadyOnly',
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SettingsUpdate(StrictModel):
    comfyUiUrl: str | None = Field(default=None, max_length=2048)
    defaultImageWorkflowId: str | None = Field(default=None, max_length=200)
    defaultVideoWorkflowId: str | None = Field(default=None, max_length=200)
    productionVideoWorkflowId: str | None = Field(default=None, max_length=200)
    showReadyOnly: bool | None = None

    @field_validator('comfyUiUrl')
    @classmethod
    def validate_comfy_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip('/')
        parsed = urlparse(normalized)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('ComfyUI 地址必须是无认证信息的 HTTP(S) URL')
        if parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
            raise ValueError('ComfyUI 地址不能包含路径、查询参数或片段')
        return normalized

    @field_validator('defaultImageWorkflowId', 'defaultVideoWorkflowId', 'productionVideoWorkflowId')
    @classmethod
    def normalize_workflow_id(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


def _decode(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw


def read_overrides(db: Database) -> dict[str, Any]:
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT key,value FROM settings WHERE key IN ({','.join('?' for _ in SETTING_KEYS)})",
            tuple(sorted(SETTING_KEYS)),
        ).fetchall()
    return {str(row['key']): _decode(row['value']) for row in rows}


def write_overrides(db: Database, values: dict[str, Any]) -> None:
    unknown = set(values) - SETTING_KEYS
    if unknown:
        raise ValueError(f'Unsupported settings: {sorted(unknown)}')
    with db.connect() as conn:
        for key, value in values.items():
            if value is None:
                conn.execute('DELETE FROM settings WHERE key=?', (key,))
            else:
                conn.execute(
                    "INSERT INTO settings(key,value,updated_at) VALUES(?,?,datetime('now')) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (key, json.dumps(value, ensure_ascii=False)),
                )


def effective_comfy_url(db: Database | None = None) -> tuple[str, str]:
    selected_db = db or Database(DEFAULT_DB)
    if selected_db.path.is_file():
        try:
            value = read_overrides(selected_db).get('comfyUiUrl')
            if isinstance(value, str) and value.strip():
                return value.strip().rstrip('/'), 'local_override'
        except Exception:
            pass
    environment = os.getenv('COMFYUI_URL', '').strip()
    if environment:
        return environment.rstrip('/'), 'environment'
    return 'http://127.0.0.1:8188', 'default'


def path_status(key: str, label: str, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    exists = resolved.exists()
    probe = resolved if exists else next((parent for parent in resolved.parents if parent.exists()), ROOT)
    return {
        'key': key,
        'label': label,
        'path': str(resolved),
        'exists': exists,
        'writable': os.access(probe, os.W_OK),
        'editable': False,
        'source': 'system_managed',
    }


def storage_status() -> list[dict[str, Any]]:
    return [
        path_status('workflowPackages', '工作流 Package 目录', ROOT / 'storage' / 'workflow-packages'),
        path_status('outputs', '生成输出目录', ROOT / 'storage' / 'outputs'),
        path_status('materials', '素材目录', ROOT / 'storage' / 'materials'),
        path_status('gptDirector', 'GPT Director 存储目录', ROOT / 'storage' / 'gpt-director'),
        path_status('gptImage', 'GPT Image 存储目录', ROOT / 'storage' / 'gpt-image-jobs'),
        path_status('temporary', '临时缓存目录', ROOT / 'storage' / 'chatgpt-image-worker'),
    ]
