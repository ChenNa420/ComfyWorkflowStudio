from __future__ import annotations

import json
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.comfy.client import ComfyClient, ComfyClientError, comfy_url_from_env
from backend.comfy.converter import NON_EXECUTION_NODE_TYPES
from backend.models import WorkflowManifest
from backend.workflow.manifest import discover_manifests

MODEL_EXTENSIONS = ('.safetensors', '.ckpt', '.pt', '.pth', '.onnx', '.gguf', '.bin')
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


def _load_original(manifest_path: Path) -> dict[str, Any] | None:
    original_path = manifest_path.parent / 'original.json'
    if not original_path.is_file():
        return None
    try:
        value = json.loads(original_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_strings(child)


def classify_model_type(node_type: str, field_name: str, model_name: str) -> str:
    field = field_name.casefold().replace('-', '_')
    if any(token in field for token in ('control_net', 'controlnet')):
        return 'controlnet'
    if 'lora' in field:
        return 'lora'
    if 'clip_vision' in field or 'vision_model' in field:
        return 'vision'
    if any(token in field for token in ('text_encoder', 'clip_name')):
        return 'text-encoder'
    if 'vae' in field:
        return 'vae'
    if any(token in field for token in ('upscale_model', 'upscalemodel')):
        return 'upscaler'
    if any(token in field for token in ('ckpt_name', 'checkpoint')):
        return 'checkpoint'
    if any(token in field for token in ('unet_name', 'diffusion_model', 'transformer_model')):
        return 'diffusion-model'

    text = f'{node_type} {model_name}'.casefold().replace('-', '_')
    if any(token in text for token in ('control_net', 'controlnet')):
        return 'controlnet'
    if 'lora' in text:
        return 'lora'
    if 'clip_vision' in text or 'vision_model' in text:
        return 'vision'
    if any(token in text for token in ('text_encoder', 'clip_name', 'cliploader', 'dualclip', 'tripleclip')):
        return 'text-encoder'
    if 'vae' in text:
        return 'vae'
    if any(token in text for token in ('upscale_model', 'upscalemodel', 'esrgan')):
        return 'upscaler'
    if any(token in text for token in ('ipadapter', 'instantid', 'pulid', 'adapter_model')):
        return 'adapter'
    if any(token in text for token in ('vocoder', 'tts', 'voice_model', 'audio_model', 'speech_model')):
        return 'audio'
    if any(token in text for token in ('ckpt_name', 'checkpoint', 'checkpointloader')):
        return 'checkpoint'
    if any(token in text for token in ('unet_name', 'diffusion_model', 'diffusionmodel', 'transformer_model', 'wanvideomodel', 'ggufloader')):
        return 'diffusion-model'
    return 'other'


def _primary_model_type(model_types: list[str], inferred_type: str) -> str:
    if inferred_type != 'other' and inferred_type in model_types:
        return inferred_type
    return next((value for value in model_types if value != 'other'), inferred_type)


def extract_comfy_model_catalog(object_info: dict[str, Any]) -> list[dict[str, str]]:
    """Return model options exposed by ComfyUI, with deterministic type hints.

    The catalog is built only from `/object_info`. It does not scan arbitrary
    directories or mutate the user's ComfyUI installation.
    """
    items: dict[tuple[str, str], dict[str, str]] = {}
    for node_type, definition in object_info.items():
        if not isinstance(definition, dict):
            continue
        inputs = definition.get('input')
        if not isinstance(inputs, dict):
            continue
        for section_name in ('required', 'optional', 'hidden'):
            section = inputs.get(section_name)
            if not isinstance(section, dict):
                continue
            for field_name, spec in section.items():
                for text in _walk_strings(spec):
                    normalized = text.replace('\\', '/').strip()
                    if not normalized.lower().endswith(MODEL_EXTENSIONS):
                        continue
                    model_type = classify_model_type(str(node_type), str(field_name), normalized)
                    key = (_normalize(normalized), model_type)
                    items.setdefault(key, {
                        'name': normalized,
                        'modelType': model_type,
                        'nodeType': str(node_type),
                        'field': str(field_name),
                    })
    result = list(items.values())
    result.sort(key=lambda item: (item['modelType'], item['name'].casefold()))
    return result


def extract_comfy_model_options(object_info: dict[str, Any]) -> set[str]:
    return {item['name'] for item in extract_comfy_model_catalog(object_info)}


def _catalog_matches(name: str, catalog: list[dict[str, str]], *, basename: bool = False) -> list[dict[str, str]]:
    declared = _basename(name) if basename else _normalize(name)
    result: list[dict[str, str]] = []
    for item in catalog:
        candidate = _basename(item['name']) if basename else _normalize(item['name'])
        if candidate == declared:
            result.append(item)
    return result


def match_declared_model(
    name: str,
    available: set[str],
    catalog: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    declared = _normalize(name)
    declared_base = _basename(name)
    exact = {_normalize(item): item for item in available}
    catalog = catalog or []
    inferred_type = classify_model_type('', '', name)
    if declared in exact:
        catalog_matches = _catalog_matches(name, catalog)
        model_types = sorted({item['modelType'] for item in catalog_matches})
        return {
            'status': 'PRESENT',
            'matched': exact[declared],
            'match': 'exact',
            'modelType': _primary_model_type(model_types, inferred_type),
            'modelTypes': model_types or [inferred_type],
        }
    basename_matches = [item for item in available if _basename(item) == declared_base]
    if basename_matches:
        catalog_matches = _catalog_matches(name, catalog, basename=True)
        model_types = sorted({item['modelType'] for item in catalog_matches})
        payload = {
            'status': 'PRESENT',
            'matched': basename_matches[0],
            'match': 'basename' if len(basename_matches) == 1 else 'basename-ambiguous',
            'modelType': _primary_model_type(model_types, inferred_type),
            'modelTypes': model_types or [inferred_type],
        }
        if len(basename_matches) > 1:
            payload['alternatives'] = basename_matches[:20]
        return payload
    return {
        'status': 'MISSING',
        'matched': None,
        'match': None,
        'modelType': inferred_type,
        'modelTypes': [inferred_type],
    }


def _has_output_links(node: dict[str, Any]) -> bool:
    for output in node.get('outputs') or []:
        if isinstance(output, dict) and output.get('links'):
            return True
    return False


def _node_mode(node: dict[str, Any]) -> int:
    try:
        return int(node.get('mode') or 0)
    except (TypeError, ValueError):
        return 0


def execution_node_types(
    manifest_path: Path,
    analysis: dict[str, Any],
    *,
    connected: bool,
    object_info: dict[str, Any],
) -> tuple[list[str], list[dict[str, str]]]:
    """Return node types that can actually block runtime conversion.

    This intentionally mirrors `ui_workflow_to_prompt` safety semantics:
    known note/label nodes and `mode=2` nodes are not executable, while an
    unknown UI node with no downstream output links is treated as decoration
    rather than a missing runtime dependency.
    """
    original = _load_original(manifest_path)
    required: list[str] = []
    ignored: list[dict[str, str]] = []

    if isinstance(original, dict) and isinstance(original.get('nodes'), list):
        for raw in original.get('nodes') or []:
            if not isinstance(raw, dict):
                continue
            node_type = str(raw.get('type') or '').strip()
            if not node_type:
                continue
            if node_type in NON_EXECUTION_NODE_TYPES:
                ignored.append({'nodeType': node_type, 'reason': 'known-non-execution'})
                continue
            if _node_mode(raw) == 2:
                ignored.append({'nodeType': node_type, 'reason': 'mode-never'})
                continue
            if connected and node_type not in object_info and not _has_output_links(raw):
                ignored.append({'nodeType': node_type, 'reason': 'unconnected-ui-only'})
                continue
            required.append(node_type)
    elif isinstance(original, dict) and original and all(isinstance(value, dict) for value in original.values()):
        for value in original.values():
            node_type = str(value.get('class_type') or '').strip()
            if not node_type:
                continue
            if node_type in NON_EXECUTION_NODE_TYPES:
                ignored.append({'nodeType': node_type, 'reason': 'known-non-execution'})
                continue
            required.append(node_type)
    else:
        for value in analysis.get('nodeTypes') or []:
            node_type = str(value).strip()
            if not node_type:
                continue
            if node_type in NON_EXECUTION_NODE_TYPES:
                ignored.append({'nodeType': node_type, 'reason': 'known-non-execution'})
                continue
            required.append(node_type)

    return list(dict.fromkeys(required)), ignored


def _workflow_dependency_item(
    manifest_path: Path,
    manifest: WorkflowManifest,
    *,
    connected: bool,
    object_info: dict[str, Any],
    available_models: set[str],
    model_catalog: list[dict[str, str]],
) -> dict[str, Any]:
    analysis = _load_analysis(manifest_path)
    node_types, ignored_node_types = execution_node_types(
        manifest_path,
        analysis,
        connected=connected,
        object_info=object_info,
    )

    model_items: list[dict[str, Any]] = []
    for dependency in manifest.dependencies.models:
        if connected:
            match = match_declared_model(dependency.name, available_models, model_catalog)
        else:
            inferred_type = classify_model_type('', '', dependency.name)
            match = {
                'status': 'UNKNOWN',
                'matched': None,
                'match': None,
                'modelType': inferred_type,
                'modelTypes': [inferred_type],
            }
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
            'executionRequired': True,
        }
        for node_type in node_types
    ]

    package_items = [
        {
            'name': item.name,
            'required': item.required,
            'installUrl': item.installUrl,
            'status': 'DECLARED',
            'verification': 'execution-node-types',
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
        'ignoredNodeTypes': ignored_node_types,
        'customNodePackages': package_items,
        'counts': {
            'models': len(model_items),
            'missingModels': len(missing_models),
            'nodeTypes': len(node_items),
            'missingNodeTypes': len(missing_nodes),
            'ignoredNodeTypes': len(ignored_node_types),
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

    model_catalog = extract_comfy_model_catalog(object_info) if connected else []
    available_models = {item['name'] for item in model_catalog}
    workflows = [
        _workflow_dependency_item(
            path,
            manifest,
            connected=connected,
            object_info=object_info,
            available_models=available_models,
            model_catalog=model_catalog,
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
                'modelType': item.get('modelType') or 'other',
                'modelTypes': list(item.get('modelTypes') or [item.get('modelType') or 'other']),
                'workflows': [],
            })
            for model_type in item.get('modelTypes') or []:
                if model_type not in entry['modelTypes']:
                    entry['modelTypes'].append(model_type)
            if item['status'] == 'PRESENT':
                entry['status'] = 'PRESENT'
                entry['matched'] = item.get('matched')
                if item.get('modelType') and item.get('modelType') != 'other':
                    entry['modelType'] = item['modelType']
            elif entry['status'] != 'PRESENT' and item['status'] == 'MISSING':
                entry['status'] = 'MISSING'
            entry['workflows'].append({'id': workflow['workflowId'], 'name': workflow['name']})

    node_usage: dict[str, list[dict[str, str]]] = defaultdict(list)
    ignored_usage: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for workflow in workflows:
        for item in workflow['nodeTypes']:
            node_usage[item['nodeType']].append({'id': workflow['workflowId'], 'name': workflow['name']})
        for item in workflow.get('ignoredNodeTypes') or []:
            ignored_usage[(item['nodeType'], item['reason'])].append({'id': workflow['workflowId'], 'name': workflow['name']})

    model_rows = sorted(model_usage.values(), key=lambda item: (item['status'] != 'MISSING', item['modelType'], item['name'].casefold()))
    node_rows = [
        {
            'nodeType': node_type,
            'status': 'PRESENT' if connected and node_type in object_info else 'MISSING' if connected else 'UNKNOWN',
            'workflows': usage,
        }
        for node_type, usage in node_usage.items()
    ]
    node_rows.sort(key=lambda item: (item['status'] != 'MISSING', item['nodeType'].casefold()))
    ignored_rows = [
        {
            'nodeType': node_type,
            'reason': reason,
            'workflows': usage,
            'workflowCount': len(usage),
        }
        for (node_type, reason), usage in ignored_usage.items()
    ]
    ignored_rows.sort(key=lambda item: (-item['workflowCount'], item['nodeType'].casefold()))

    status_counts = Counter(item['status'] for item in workflows)
    type_counts = Counter(
        model_type
        for item in model_rows
        for model_type in (item.get('modelTypes') or [item['modelType']])
    )
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
            'ignoredNodeTypes': len({item['nodeType'] for item in ignored_rows}),
            'ignoredNodeOccurrences': sum(item['workflowCount'] for item in ignored_rows),
            'modelTypes': [{'key': key, 'count': count} for key, count in type_counts.most_common()],
        },
        'workflows': workflows,
        'models': model_rows,
        'nodeTypes': node_rows,
        'ignoredNodeTypes': ignored_rows,
        'modelCatalog': model_catalog,
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
