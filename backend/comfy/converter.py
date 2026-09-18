from __future__ import annotations

from collections import OrderedDict
from typing import Any


class WorkflowConversionError(RuntimeError):
    pass


NON_EXECUTION_NODE_TYPES = {
    'PixaromaNote',
    'PixaromaLabel',
    'Note',
    'MarkdownNote',
}

PRIMITIVE_WIDGET_TYPES = {'INT', 'FLOAT', 'BOOLEAN', 'STRING'}


def _flatten_state(value: Any, result: dict[str, Any] | None = None) -> dict[str, Any]:
    output = result or {}
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, dict):
                _flatten_state(item, output)
            elif isinstance(item, (str, int, float, bool)) or item is None:
                output[str(key).lower()] = item
    return output


def _input_schema(info: dict[str, Any]) -> OrderedDict[str, Any]:
    result: OrderedDict[str, Any] = OrderedDict()
    input_info = info.get('input') or {}
    for group in ('required', 'optional'):
        values = input_info.get(group) or {}
        if isinstance(values, dict):
            for key, spec in values.items():
                result[str(key)] = spec
    return result


def _spec_kind(spec: Any) -> Any:
    if isinstance(spec, (list, tuple)) and spec:
        return spec[0]
    return None


def _spec_options(spec: Any) -> dict[str, Any]:
    if isinstance(spec, (list, tuple)) and len(spec) > 1 and isinstance(spec[1], dict):
        return spec[1]
    return {}


def _is_widget_spec(spec: Any) -> bool:
    kind = _spec_kind(spec)
    return isinstance(kind, list) or kind in PRIMITIVE_WIDGET_TYPES


def _compatible(value: Any, spec: Any) -> bool:
    kind = _spec_kind(spec)
    if isinstance(kind, list):
        return value in kind
    if kind == 'INT':
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == 'FLOAT':
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == 'BOOLEAN':
        return isinstance(value, bool)
    if kind == 'STRING':
        return isinstance(value, str)
    # IMAGE / MODEL / LATENT / CONDITIONING and other unknown kinds are
    # connection types. Never guess them from arbitrary widget values.
    return False


def _default_for_spec(spec: Any) -> tuple[bool, Any]:
    options = _spec_options(spec)
    if 'default' in options:
        return True, options['default']
    kind = _spec_kind(spec)
    if isinstance(kind, list) and kind:
        return True, kind[0]
    return False, None


def _state_value(field: str, state: dict[str, Any]) -> tuple[bool, Any]:
    key = field.lower()
    aliases = {
        'duration': ('duration', 'seconds'),
        'seconds': ('seconds', 'duration'),
        'fps': ('fps',),
        'frames': ('frames',),
        'length': ('length', 'frames'),
        'size': ('size',),
        'longest_side': ('size', 'longestside'),
        'ratio': ('ratio',),
        'allow_upscale': ('allow_upscale',),
        'resample': ('resample',),
        'text': ('text', 'lastrun'),
        'text_in': ('text', 'lastrun'),
        'prompt': ('text', 'lastrun'),
        'image': ('image',),
    }
    for candidate in aliases.get(key, (key,)):
        if candidate in state:
            return True, state[candidate]
    return False, None


def ui_workflow_to_prompt(workflow: dict[str, Any], object_info: dict[str, Any]) -> dict[str, Any]:
    nodes = workflow.get('nodes') or []
    links = workflow.get('links') or []
    link_map: dict[int, list[Any]] = {}
    for link in links:
        if isinstance(link, list) and len(link) >= 5:
            try:
                link_map[int(link[0])] = link
            except (TypeError, ValueError):
                continue

    prompt: dict[str, Any] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get('id'))
        class_type = str(node.get('type') or '')
        if not class_type:
            continue
        if class_type in NON_EXECUTION_NODE_TYPES:
            continue
        mode = int(node.get('mode') or 0)
        if mode == 2:  # Never
            continue
        if mode not in (0,):
            raise WorkflowConversionError(f'Node {node_id} ({class_type}) uses unsupported mode {mode}; review required')

        info = object_info.get(class_type)
        if not isinstance(info, dict):
            # Pure UI decoration / timer nodes can be safely ignored if they do
            # not feed any downstream links.
            has_output_links = any((out.get('links') or []) for out in (node.get('outputs') or []) if isinstance(out, dict))
            if not has_output_links:
                continue
            raise WorkflowConversionError(f'ComfyUI does not report node type {class_type}; custom node may be missing')

        schema = _input_schema(info)
        linked_by_name: dict[str, Any] = {}
        for ui_input in node.get('inputs') or []:
            if not isinstance(ui_input, dict):
                continue
            link_id = ui_input.get('link')
            if link_id is None:
                continue
            try:
                link = link_map[int(link_id)]
            except (KeyError, TypeError, ValueError):
                continue
            linked_by_name[str(ui_input.get('name') or '')] = [str(link[1]), int(link[2])]

        values = list(node.get('widgets_values') or [])
        state = _flatten_state(node.get('properties') or {})
        api_inputs: dict[str, Any] = {}
        widget_index = 0

        for field, spec in schema.items():
            if field in linked_by_name:
                api_inputs[field] = linked_by_name[field]
                continue

            found_state, state_candidate = _state_value(field, state)
            if found_state and _compatible(state_candidate, spec):
                api_inputs[field] = state_candidate
                continue

            # Connection-only inputs must never consume widget values. This is
            # especially important for optional inputs such as last_frame: if it
            # is unlinked we leave it absent and preserve width/height/length
            # widgets for the primitive fields that follow.
            if not _is_widget_spec(spec):
                required = field in ((info.get('input') or {}).get('required') or {})
                if required:
                    raise WorkflowConversionError(f'Cannot map required connection {field} on node {node_id} ({class_type})')
                continue

            matched = False
            while widget_index < len(values):
                candidate = values[widget_index]
                widget_index += 1
                if _compatible(candidate, spec):
                    api_inputs[field] = candidate
                    matched = True
                    break
            if matched:
                continue

            has_default, default_value = _default_for_spec(spec)
            if has_default:
                api_inputs[field] = default_value
                continue

            required = field in ((info.get('input') or {}).get('required') or {})
            if required:
                raise WorkflowConversionError(f'Cannot map required input {field} on node {node_id} ({class_type})')

        prompt[node_id] = {'class_type': class_type, 'inputs': api_inputs}

    if not prompt:
        raise WorkflowConversionError('Workflow did not contain executable nodes')
    return prompt
