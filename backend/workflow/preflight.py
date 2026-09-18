from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from backend.comfy.client import ComfyClient, ComfyClientError, comfy_url_from_env
from backend.comfy.converter import WorkflowConversionError, ui_workflow_to_prompt
from backend.comfy.runtime import _resolve_prompt_field
from backend.db import Database
from backend.models import WorkflowManifest
from backend.workflow.dependencies import dependency_inventory, dependency_workflow
from backend.workflow.manifest import discover_manifests

PREFLIGHT_CERTIFIED = 'CERTIFIED'
PREFLIGHT_NEEDS_REVIEW = 'NEEDS_REVIEW'
PREFLIGHT_BLOCKED = 'BLOCKED_DEPENDENCIES'
PREFLIGHT_OFFLINE = 'COMFY_OFFLINE'


def _workflow_rows(db: Database) -> dict[str, dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            'SELECT id, original_path, api_workflow_path, enabled FROM workflows'
        ).fetchall()
    return {str(row['id']): dict(row) for row in rows}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('workflow_json_must_be_object')
    return value


def _source_path(manifest_path: Path, db_row: dict[str, Any] | None) -> Path | None:
    if db_row:
        for raw in (db_row.get('api_workflow_path'), db_row.get('original_path')):
            if raw:
                path = Path(str(raw))
                if path.is_file():
                    return path
    for name in ('workflow-api.json', 'original.json'):
        path = manifest_path.parent / name
        if path.is_file():
            return path
    return None


def _issue(code: str, message: str, *, severity: str = 'ERROR', **data: Any) -> dict[str, Any]:
    return {'code': code, 'message': message, 'severity': severity, **data}


def _validate_manifest_mappings(
    manifest: WorkflowManifest,
    prompt: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for item in manifest.inputs:
        mapping = item.mapping
        if item.required and (not mapping.nodeId or not mapping.field):
            errors.append(
                _issue(
                    'REQUIRED_INPUT_MAPPING_MISSING',
                    f'必填输入 {item.label or item.key} 缺少 Node/Field 映射。',
                    inputKey=item.key,
                )
            )
            continue
        if not mapping.nodeId:
            continue
        node = prompt.get(str(mapping.nodeId))
        if not isinstance(node, dict):
            errors.append(
                _issue(
                    'INPUT_NODE_MISSING',
                    f'输入 {item.label or item.key} 指向不存在的 Node {mapping.nodeId}。',
                    inputKey=item.key,
                    nodeId=str(mapping.nodeId),
                )
            )
            continue
        node_inputs = node.get('inputs') if isinstance(node.get('inputs'), dict) else {}
        field = _resolve_prompt_field(node_inputs, mapping.field)
        if mapping.field and field not in node_inputs:
            errors.append(
                _issue(
                    'INPUT_FIELD_MISSING',
                    f'输入 {item.label or item.key} 的字段 {mapping.field} 在 Runtime Prompt 中不存在。',
                    inputKey=item.key,
                    nodeId=str(mapping.nodeId),
                    field=mapping.field,
                )
            )

    for item in manifest.parameters:
        mapping = item.mapping
        runtime_duration = manifest.runtime.durationPolicy == 'dynamic' and (
            mapping.strategy == 'duration-to-frames'
            or item.key.lower() in {'duration', 'seconds', 'duration_seconds', 'video_duration'}
        )
        if not mapping.nodeId:
            warnings.append(
                _issue(
                    'PARAMETER_MAPPING_MISSING',
                    f'参数 {item.label or item.key} 未映射到 Runtime Prompt。',
                    severity='WARNING',
                    parameterKey=item.key,
                )
            )
            continue
        node = prompt.get(str(mapping.nodeId))
        if not isinstance(node, dict):
            # Runtime applies dynamic duration across the converted prompt from
            # durationState metadata. Its UI helper node may intentionally be
            # removed by the converter, so that node is not a required target.
            if runtime_duration:
                continue
            errors.append(
                _issue(
                    'PARAMETER_NODE_MISSING',
                    f'参数 {item.label or item.key} 指向不存在的 Node {mapping.nodeId}。',
                    parameterKey=item.key,
                    nodeId=str(mapping.nodeId),
                )
            )
            continue
        node_inputs = node.get('inputs') if isinstance(node.get('inputs'), dict) else {}
        field = _resolve_prompt_field(node_inputs, mapping.field)
        if mapping.field and field not in node_inputs:
            if runtime_duration:
                continue
            errors.append(
                _issue(
                    'PARAMETER_FIELD_MISSING',
                    f'参数 {item.label or item.key} 的字段 {mapping.field} 在 Runtime Prompt 中不存在。',
                    parameterKey=item.key,
                    nodeId=str(mapping.nodeId),
                    field=mapping.field,
                )
            )

    if manifest.runtime.durationPolicy == 'dynamic':
        has_duration = any(
            item.mapping.strategy == 'duration-to-frames'
            or item.key.lower() in {'duration', 'seconds', 'duration_seconds', 'video_duration'}
            for item in manifest.parameters
        )
        if not has_duration:
            warnings.append(
                _issue(
                    'DYNAMIC_DURATION_PARAMETER_MISSING',
                    'Workflow 声明 dynamic duration，但 Manifest 没有明确的时长参数。',
                    severity='WARNING',
                )
            )

    if manifest.runtime.executionMode != 'serial':
        warnings.append(_issue('RUNTIME_NOT_SERIAL', 'Runtime executionMode 不是 serial。', severity='WARNING'))
    if manifest.runtime.retryUnknown:
        errors.append(_issue('UNKNOWN_RETRY_ENABLED', 'retryUnknown 必须为 false。'))
    if not manifest.runtime.preserveOriginalWorkflow:
        errors.append(_issue('ORIGINAL_NOT_PRESERVED', 'preserveOriginalWorkflow 必须为 true。'))

    return errors, warnings


def _validate_outputs(
    manifest: WorkflowManifest,
    prompt: dict[str, Any],
    object_info: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    detected_output_nodes: list[str] = []

    for node_id, node in prompt.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get('class_type') or '')
        info = object_info.get(class_type)
        if isinstance(info, dict) and bool(info.get('output_node')):
            detected_output_nodes.append(str(node_id))

    if not manifest.outputs:
        warnings.append(_issue('MANIFEST_OUTPUTS_EMPTY', 'Manifest 未声明输出。', severity='WARNING'))

    for output in manifest.outputs:
        node_id = output.mapping.nodeId
        if not node_id:
            if not detected_output_nodes:
                errors.append(
                    _issue(
                        'OUTPUT_NODE_UNRESOLVED',
                        f'输出 {output.key} 没有 Node 映射，且 Runtime Prompt 未检测到 output_node。',
                        outputKey=output.key,
                    )
                )
            else:
                warnings.append(
                    _issue(
                        'OUTPUT_MAPPING_INFERRED',
                        f'输出 {output.key} 未显式映射，将依赖 Runtime output_node。',
                        severity='WARNING',
                        outputKey=output.key,
                        detectedOutputNodes=detected_output_nodes,
                    )
                )
            continue
        if str(node_id) not in prompt:
            errors.append(
                _issue(
                    'OUTPUT_NODE_MISSING',
                    f'输出 {output.key} 指向不存在的 Node {node_id}。',
                    outputKey=output.key,
                    nodeId=str(node_id),
                )
            )

    if not detected_output_nodes and not any(output.mapping.nodeId for output in manifest.outputs):
        errors.append(_issue('NO_RUNTIME_OUTPUT_NODE', 'Runtime Prompt 没有可确认的输出节点。'))

    return errors, warnings, detected_output_nodes


def _convert_source(source: dict[str, Any], object_info: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if isinstance(source.get('nodes'), list):
        return ui_workflow_to_prompt(source, object_info), 'ui-workflow'
    prompt = json.loads(json.dumps(source))
    if not prompt:
        raise WorkflowConversionError('Workflow prompt is empty')
    return prompt, 'api-workflow'


def preflight_one(
    manifest: WorkflowManifest,
    manifest_path: Path,
    *,
    db_row: dict[str, Any] | None,
    dependency: dict[str, Any] | None,
    object_info: dict[str, Any] | None,
) -> dict[str, Any]:
    dependency_status = str((dependency or {}).get('status') or 'UNKNOWN')
    base = {
        'workflowId': manifest.workflowId,
        'name': manifest.name,
        'category': manifest.category,
        'capabilities': list(manifest.capabilities),
        'dependencyStatus': dependency_status,
        'status': PREFLIGHT_NEEDS_REVIEW,
        'sourceFormat': None,
        'sourcePath': None,
        'promptNodes': 0,
        'detectedOutputNodes': [],
        'errors': [],
        'warnings': [],
        'writeMode': False,
        'submitsPrompt': False,
    }

    if object_info is None:
        base['status'] = PREFLIGHT_OFFLINE
        base['warnings'] = [_issue('COMFY_OFFLINE', 'ComfyUI 离线，无法执行 Runtime 结构预检。', severity='WARNING')]
        return base

    if dependency_status == 'MISSING_DEPENDENCIES':
        base['status'] = PREFLIGHT_BLOCKED
        base['errors'] = [_issue('MISSING_DEPENDENCIES', '真实运行依赖尚未满足，跳过 Runtime 转换认证。')]
        return base

    source_path = _source_path(manifest_path, db_row)
    if source_path is None:
        base['errors'] = [_issue('WORKFLOW_FILE_MISSING', '找不到可用于 Runtime 的 Workflow JSON。')]
        return base
    base['sourcePath'] = str(source_path)

    try:
        source = _load_json(source_path)
        prompt, source_format = _convert_source(source, object_info)
    except (OSError, json.JSONDecodeError, ValueError, WorkflowConversionError) as exc:
        base['errors'] = [_issue('CONVERSION_FAILED', str(exc))]
        return base

    base['sourceFormat'] = source_format
    base['promptNodes'] = len(prompt)

    errors, warnings = _validate_manifest_mappings(manifest, prompt)
    output_errors, output_warnings, output_nodes = _validate_outputs(manifest, prompt, object_info)
    errors.extend(output_errors)
    warnings.extend(output_warnings)
    base['detectedOutputNodes'] = output_nodes
    base['errors'] = errors
    base['warnings'] = warnings
    base['status'] = PREFLIGHT_CERTIFIED if not errors else PREFLIGHT_NEEDS_REVIEW
    return base


def preflight_report(
    db: Database,
    *,
    capability: str | None = None,
    category: str | None = None,
    certified_only: bool = False,
    force_refresh: bool = False,
    limit: int = 500,
) -> dict[str, Any]:
    inventory = dependency_inventory(force_refresh=force_refresh)
    object_info: dict[str, Any] | None = None
    object_error: str | None = None
    if inventory.get('connected'):
        try:
            object_info = ComfyClient(comfy_url_from_env(), timeout=20).object_info()
        except ComfyClientError as exc:
            object_error = str(exc)

    rows = _workflow_rows(db)
    results: list[dict[str, Any]] = []
    for manifest_path, manifest in discover_manifests():
        if capability and capability not in manifest.capabilities:
            continue
        if category and manifest.category != category:
            continue
        dependency = dependency_workflow(inventory, manifest.workflowId)
        item = preflight_one(
            manifest,
            manifest_path,
            db_row=rows.get(manifest.workflowId),
            dependency=dependency,
            object_info=object_info,
        )
        if certified_only and item['status'] != PREFLIGHT_CERTIFIED:
            continue
        results.append(item)

    status_counts = Counter(item['status'] for item in results)
    error_codes = Counter(
        issue['code']
        for item in results
        for issue in item.get('errors') or []
    )
    warning_codes = Counter(
        issue['code']
        for item in results
        for issue in item.get('warnings') or []
    )
    results.sort(
        key=lambda item: (
            0 if item['status'] == PREFLIGHT_CERTIFIED else 1 if item['status'] == PREFLIGHT_NEEDS_REVIEW else 2,
            item['name'].casefold(),
        )
    )
    selected = results[: max(1, min(limit, 1000))]
    return {
        'connected': object_info is not None,
        'comfyUiUrl': inventory.get('comfyUiUrl'),
        'error': object_error or inventory.get('error'),
        'filters': {
            'capability': capability,
            'category': category,
            'certifiedOnly': certified_only,
        },
        'summary': {
            'workflows': len(results),
            'certified': status_counts.get(PREFLIGHT_CERTIFIED, 0),
            'needsReview': status_counts.get(PREFLIGHT_NEEDS_REVIEW, 0),
            'blockedDependencies': status_counts.get(PREFLIGHT_BLOCKED, 0),
            'offline': status_counts.get(PREFLIGHT_OFFLINE, 0),
            'errorCodes': [{'key': key, 'count': count} for key, count in error_codes.most_common()],
            'warningCodes': [{'key': key, 'count': count} for key, count in warning_codes.most_common()],
        },
        'items': selected,
        'rules': [
            'Preflight 只做本地静态/Runtime 结构认证，不向 ComfyUI 提交 prompt。',
            'CERTIFIED 表示依赖、转换、必填输入映射、输出节点与关键 Runtime 安全规则通过；不等于已完成真实生成。',
            '任何转换失败、映射失效或输出节点无法确认都会进入 NEEDS_REVIEW。',
            'ComfyUI 离线时不生成虚假认证结果。',
        ],
    }


def preflight_detail(db: Database, workflow_id: str, *, force_refresh: bool = False) -> dict[str, Any] | None:
    report = preflight_report(db, force_refresh=force_refresh, limit=1000)
    return next((item for item in report['items'] if item['workflowId'] == workflow_id), None)
