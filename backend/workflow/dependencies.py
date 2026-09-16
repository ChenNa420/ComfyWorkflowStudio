from __future__ import annotations

import json
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.comfy.client import ComfyClient, ComfyClientError, comfy_url_from_env
from backend.models import WorkflowManifest
from backend.workflow.manifest import discover_manifests

MODEL_EXTENSIONS = ('.safetensors', '.ckpt', '.pt', '.pth', '.onnx', '.gguf', '.bin')
IGNORED_NODE_TYPES = {'PixaromaNote', 'PixaromaLabel'}
_CACHE_TTL_SECONDS = 5.0
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {'key': None, 'at': 0.0, 'value': None}


def _normalize(value: str) -> str:
    return value.replace('\\', '/').strip().casefold()


def _basename(value: str) -> str:
    return _normalize(value).rsplit('/', 1)[-1]


def _load_analysis(manifest_path: Path) -> dict[str, Any]:
    analysis_path = manifest_path.parent / 'analysis.json'
    if not analysis_path.is_file():
        return {}
    try:
        value = json.loads(analysis_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_strings(child)


def extract_comfy_model_options(object_info: dict[str, Any]) -> set[str]:
    """Collect model filenames exposed by ComfyUI node input enums.

    This intentionally uses `/object_info` instead of scanning arbitrary local
    directories, so Phase 1F stays read-only and respects the active ComfyUI
    installation's own model registry.
    """
    result: set[str] = set()
    for definition in object_info.values():
        if not isinstance(definition, dict):
            continue
        inputs = definition.get('input')
        if not isinstance(inputs, dict):
            continue
        for text in _walk_strings(inputs):
            normalized = text.replace('\\', '/').strip()
            if normalized.lower().endswith(MODEL_EXTENSIONS):
                result.add(normalized)
    return result


def match_declared_model(name: str, available: set[str]) -> dict[str, Any]:
    declared = _normalize(name)
    declared_base = _basename(name)
    exact = {_normalize(item): item for item in available}
    if declared in exact:
        return {'status': 'PRESENT', 'matched': exact[declared], 'match': 'exact'}
    basename_matches = [item for item in available if _basename(item) == declared_base]
    if len(basename_matches) == 1:
        return {'status': 'PRESENT', 'matched': basename_matches[0], 'match': 'basename'}
    if len(basename_matches) > 1:
        return {'status': 'PRESENT', 'matched': basename_matches[0], 'match': 'basename-ambiguous', 'alternatives': basename_matches[:20]}
    return {'status': 'MISSING', 'matched': None, 'match': None}


def _workflow_dependency_item(
    manifest_path: Path,
    manifest: WorkflowManifest,
    *,
    connected: bool,
    object_info: dict[str, Any],
    available_models: set[str],
) -> dict[str, Any]:
    analysis = _load_analysis(manifest_path)
    node_types = [
        str(value) for value in (analysis.get('nodeTypes') or [])
        if str(value) and str(value) not in IGNORED_NODE_TYPES
    ]

    model_items: list[dict[str, Any]] = []
    for dependency in manifest.dependencies.models:
        if connected:
            match = match_declared_model(dependency.name, available_models)
        else:
            match = {'status': 'UNKNOWN', 'matched': None, 'match': None}
        model_items.append({
            'name': dependency.name,
            'required': dependency.required,
            'declaredPath': dependency.path,
            **match,
        })

    node_items = [
        {
            'nodeType': node_type,
            'status': 'PRESENT' if connected and node_type in object_info else 'MISSING' if connected else 'UNKNOWN',
        }
        for node_type in node_types
    ]

    package_items = [
        {
            'name': item.name,
            'required': item.required,
            'installUrl': item.installUrl,
            'status': 'DECLARED',
            'verification': 'node-types',
        }
        for item in manifest.dependencies.customNodes
    ]

    missing_models = [item for item in model_items if item['required'] and item['status'] == 'MISSING']
    missing_nodes = [item for item in node_items if item['status'] == 'MISSING']
    unknown_models = [item for item in model_items if item['required'] and item['status'] == 'UNKNOWN']

    if not connected:
        status = 'COMFY_OFFLINE'
    elif missing_nodes or missing_models:
        status = 'MISSING_DEPENDENCIES'
    elif unknown_models:
        status = 'UNKNOWN'
    else:
        status = 'READY'

    return {
        'workflowId': manifest.workflowId,
        'name': manifest.name,
        'category': manifest.category,
        'capabilities': list(manifest.capabilities),
        'status': status,
        'models': model_items,
        'nodeTypes': node_items,
        'customNodePackages': package_items,
        'counts': {
            'models': len(model_items),
            'missingModels': len(missing_models),
            'nodeTypes': len(node_items),
            'missingNodeTypes': len(missing_nodes),
            'customNodePackages': len(package_items),
        },
    }


def _build_dependency_inventory(client: ComfyClient) -> dict[str, Any]:
    object_info: dict[str, Any] = {}
    connected = False
    error = None
    try:
        object_info = client.object_info()
        connected = True
    except ComfyClientError as exc:
        error = str(exc)

    available_models = extract_comfy_model_options(object_info) if connected else set()
    workflows = [
        _workflow_dependency_item(
            path,
            manifest,
            connected=connected,
            object_info=object_info,
            available_models=available_models,
        )
        for path, manifest in discover_manifests()
    ]

    model_usage: dict[str, dict[str, Any]] = {}
    for workflow in workflows:
        for item in workflow['models']:
            key = _normalize(item['name'])
            entry = model_usage.setdefault(key, {
                'name': item['name'],
                'status': item['status'],
                'matched': item.get('matched'),
                'workflows': [],
            })
            if item['status'] == 'PRESENT':
                entry['status'] = 'PRESENT'
                entry['matched'] = item.get('matched')
            elif entry['status'] != 'PRESENT' and item['status'] == 'MISSING':
                entry['status'] = 'MISSING'
            entry['workflows'].append({'id': workflow['workflowId'], 'name': workflow['name']})

    node_usage: dict[str, list[dict[str, str]]] = defaultdict(list)
    for workflow in workflows:
        for item in workflow['nodeTypes']:
            node_usage[item['nodeType']].append({'id': workflow['workflowId'], 'name': workflow['name']})

    model_rows = sorted(model_usage.values(), key=lambda item: (item['status'] != 'MISSING', item['name'].casefold()))
    node_rows = [
        {
            'nodeType': node_type,
            'status': 'PRESENT' if connected and node_type in object_info else 'MISSING' if connected else 'UNKNOWN',
            'workflows': usage,
        }
        for node_type, usage in node_usage.items()
    ]
    node_rows.sort(key=lambda item: (item['status'] != 'MISSING', item['nodeType'].casefold()))

    status_counts = Counter(item['status'] for item in workflows)
    return {
        'connected': connected,
        'comfyUiUrl': client.base_url,
        'error': error,
        'summary': {
            'workflows': len(workflows),
            'ready': status_counts.get('READY', 0),
            'missingDependencies': status_counts.get('MISSING_DEPENDENCIES', 0),
            'offline': status_counts.get('COMFY_OFFLINE', 0),
            'declaredModels': len(model_rows),
            'availableModelOptions': len(available_models),
            'missingModels': sum(1 for item in model_rows if item['status'] == 'MISSING'),
            'requiredNodeTypes': len(node_rows),
            'missingNodeTypes': sum(1 for item in node_rows if item['status'] == 'MISSING'),
        },
        'workflows': workflows,
        'models': model_rows,
        'nodeTypes': node_rows,
    }


def dependency_inventory(*, client: ComfyClient | None = None, force_refresh: bool = False) -> dict[str, Any]:
    if client is not None:
        return _build_dependency_inventory(client)

    base_url = comfy_url_from_env()
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get('value')
        if (
            not force_refresh
            and cached is not None
            and _CACHE.get('key') == base_url
            and now - float(_CACHE.get('at') or 0) < _CACHE_TTL_SECONDS
        ):
            return cached
        value = _build_dependency_inventory(ComfyClient(base_url, timeout=20))
        _CACHE.update({'key': base_url, 'at': time.monotonic(), 'value': value})
        return value


def dependency_workflow(inventory: dict[str, Any], workflow_id: str) -> dict[str, Any] | None:
    return next((item for item in inventory.get('workflows') or [] if item.get('workflowId') == workflow_id), None)
