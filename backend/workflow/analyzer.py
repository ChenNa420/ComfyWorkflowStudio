from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

MODEL_EXTENSIONS = ('.safetensors', '.ckpt', '.pt', '.pth', '.onnx', '.gguf', '.bin')
IMAGE_NODE_HINTS = ('loadimage', 'imageinput', 'pixaromaloadimage')
OUTPUT_VIDEO_HINTS = ('savemp4', 'videocombine', 'savevideo', 'videooutput')
OUTPUT_IMAGE_HINTS = ('saveimage', 'previewimage')
OUTPUT_AUDIO_HINTS = ('saveaudio', 'audiooutput')
PROMPT_HINTS = ('prompt', 'cliptextencode', 'textencode')
DURATION_HINTS = ('duration', 'length', 'frames')


def canonical_hash(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def detect_workflow_format(data: dict[str, Any]) -> str:
    if isinstance(data.get('nodes'), list) and isinstance(data.get('links'), list):
        return 'ui-workflow'
    if data and all(isinstance(value, dict) and 'class_type' in value for value in data.values()):
        return 'api-workflow'
    return 'resource-json'


def _clean_name(filename: str) -> str:
    name = Path(filename).stem
    return re.sub(r'\s+', ' ', name).strip()


def _slug(value: str) -> str:
    value = value.lower().replace('·', '-').replace('_', '-')
    value = re.sub(r'[^a-z0-9\u4e00-\u9fff-]+', '-', value)
    return re.sub(r'-+', '-', value).strip('-') or 'workflow'


def _purpose_from_text(text: str) -> tuple[str, str, float]:
    lowered = text.lower()
    rules = [
        (('first frame', 'start frame', '首帧'), 'video-start-frame', '首帧图片', 0.98),
        (('last frame', 'end frame', '尾帧'), 'video-end-frame', '尾帧图片', 0.98),
        (('character', 'face reference', '角色'), 'character-reference', '角色参考图', 0.90),
        (('scene', 'background', '场景'), 'scene-reference', '场景参考图', 0.86),
        (('style', '风格'), 'style-reference', '风格参考图', 0.86),
        (('pose', 'openpose', '姿势'), 'pose', 'Pose 图片', 0.92),
        (('depth', '深度'), 'depth', 'Depth 图片', 0.92),
        (('lineart', 'line art', '线稿'), 'lineart', 'Lineart 图片', 0.92),
        (('mask', '蒙版'), 'mask', 'Mask 图片', 0.92),
        (('control', '控制图'), 'control-image', '控制图片', 0.78),
        (('reference', 'ref image', '参考图'), 'source-image', '参考图片', 0.68),
    ]
    for keys, purpose, label, confidence in rules:
        if any(key in lowered for key in keys):
            return purpose, label, confidence
    return 'source-image', '输入图片', 0.45


def _category_from_text(name: str, node_types: list[str]) -> tuple[str, list[str]]:
    text = f"{name} {' '.join(node_types)}".lower()
    if any(token in text for token in ('tts', 'voice', 'speech', 'cosyvoice', 'fishs2')):
        return 'tts', ['text-to-speech']
    if any(token in text for token in ('music', 'stableaudio', 'sound effect', 'audio')) and 'video' not in text:
        return 'audio', ['audio-generation']
    if any(token in text for token in ('3d', 'trellis', 'mesh', 'pixal3d')):
        return '3d', ['image-to-3d']
    if any(token in text for token in ('first frame', 'fflf', 'firstlast', 'first last')) and any(token in text for token in ('last frame', 'fflf', 'firstlast', 'first last')):
        return 'first-last-video', ['first-last-video']
    if any(token in text for token in ('image to video', 'i2v', 'img2video', 'wanvideo', 'minimaxh3imagetovideo')):
        return 'image-to-video', ['image-to-video']
    if any(token in text for token in ('text to video', 't2v')):
        return 'text-to-video', ['text-to-video']
    if any(token in text for token in ('controlnet', 'openpose', 'depth')):
        return 'controlnet', ['image-control']
    if any(token in text for token in ('inpaint', 'outpaint', 'image edit', 'edit image')):
        return 'image-edit', ['image-to-image']
    if any(token in text for token in ('text to image', 't2i', 'flux', 'sdxl')):
        return 'text-to-image', ['text-to-image']
    return 'other', ['workflow']


def _extract_models_from_values(values: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(values, str):
        if values.lower().endswith(MODEL_EXTENSIONS):
            result.add(values.replace('\\', '/'))
    elif isinstance(values, list):
        for value in values:
            result.update(_extract_models_from_values(value))
    elif isinstance(values, dict):
        for value in values.values():
            result.update(_extract_models_from_values(value))
    return result


def analyze_ui_workflow(data: dict[str, Any], filename: str) -> dict[str, Any]:
    nodes = data.get('nodes') or []
    node_types = [str(node.get('type') or '') for node in nodes]
    name = _clean_name(filename)
    category, capabilities = _category_from_text(name, node_types)

    image_inputs: list[dict[str, Any]] = []
    prompt_inputs: list[dict[str, Any]] = []
    parameters: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    models: set[str] = set()
    custom_nodes: dict[str, dict[str, Any]] = {}

    for node in nodes:
        node_id = str(node.get('id'))
        node_type = str(node.get('type') or '')
        title = str(node.get('title') or '')
        combined = f'{node_type} {title}'
        lower = combined.lower()
        properties = node.get('properties') or {}
        widgets = node.get('widgets_values') or []
        models.update(_extract_models_from_values(widgets))
        models.update(_extract_models_from_values(properties))

        cnr_id = str(properties.get('cnr_id') or '')
        if cnr_id and cnr_id != 'comfy-core':
            custom_nodes[cnr_id] = {'name': cnr_id, 'required': True}

        if any(hint in lower for hint in IMAGE_NODE_HINTS):
            purpose, label, confidence = _purpose_from_text(combined)
            image_inputs.append({
                'key': f'image_{node_id}',
                'label': label,
                'type': 'image',
                'required': True,
                'purpose': purpose,
                'description': title or node_type,
                'help': '请确认该图片输入在当前工作流中的实际用途。',
                'recommended': ['主体清晰', '尽量与目标输出比例一致'],
                'accept': ['image/png', 'image/jpeg', 'image/webp'],
                'mapping': {'nodeId': node_id, 'field': 'image'},
                'analysisConfidence': confidence,
                'nodeType': node_type,
                'nodeTitle': title,
            })

        if any(hint in lower for hint in PROMPT_HINTS):
            if node_type.lower().endswith('note') or 'label' in node_type.lower():
                pass
            else:
                prompt_inputs.append({
                    'key': f'prompt_{node_id}',
                    'label': '提示词',
                    'type': 'textarea',
                    'required': True,
                    'purpose': 'prompt',
                    'description': title or node_type,
                    'help': '描述主体动作、环境变化和镜头运动。',
                    'mapping': {'nodeId': node_id, 'field': 'text'},
                    'analysisConfidence': 0.82,
                    'nodeType': node_type,
                    'nodeTitle': title,
                })

        if any(hint in lower for hint in DURATION_HINTS):
            state = properties.get('durationState') or {}
            default = state.get('seconds', 5)
            parameters.append({
                'key': 'duration',
                'label': '视频时长',
                'type': 'number',
                'default': default,
                'min': state.get('min', 1),
                'max': state.get('max', 15),
                'step': state.get('stepSec', 0.5),
                'unit': '秒',
                'description': '最终生成视频的目标时长。',
                'mapping': {'nodeId': node_id, 'field': 'duration', 'strategy': 'duration-to-frames'},
            })

        if 'sampler' in node_type.lower() and widgets and isinstance(widgets[0], int) and not isinstance(widgets[0], bool):
            parameters.append({
                'key': 'seed',
                'label': 'Seed',
                'type': 'seed',
                'default': widgets[0],
                'description': '控制随机采样；使用相同 Seed 有助于复现结果。',
                'mapping': {'nodeId': node_id, 'field': 'seed'},
            })

        output_key = f'output_{node_id}'
        if any(hint in lower for hint in OUTPUT_VIDEO_HINTS):
            outputs.append({'key': output_key, 'type': 'video', 'format': 'mp4', 'mapping': {'nodeId': node_id}})
        elif any(hint in lower for hint in OUTPUT_IMAGE_HINTS):
            outputs.append({'key': output_key, 'type': 'image', 'format': 'png', 'mapping': {'nodeId': node_id}})
        elif any(hint in lower for hint in OUTPUT_AUDIO_HINTS):
            outputs.append({'key': output_key, 'type': 'audio', 'format': 'wav', 'mapping': {'nodeId': node_id}})

    if not outputs:
        outputs = [{'key': 'output', 'type': 'video' if 'video' in category else 'image', 'mapping': {}}]

    if not prompt_inputs and category in {'image-to-video', 'first-last-video', 'text-to-video', 'text-to-image', 'image-edit'}:
        prompt_inputs.append({
            'key': 'prompt', 'label': '提示词', 'type': 'textarea', 'required': True,
            'purpose': 'prompt', 'description': '工作流提示词', 'help': '请在适配向导中绑定真实 Prompt 节点。',
            'mapping': {}, 'analysisConfidence': 0.25, 'nodeType': '', 'nodeTitle': '',
        })

    return {
        'format': 'ui-workflow',
        'hash': canonical_hash(data),
        'name': name,
        'slug': _slug(name),
        'category': category,
        'capabilities': capabilities,
        'nodeCount': len(nodes),
        'linkCount': len(data.get('links') or []),
        'inputs': image_inputs + prompt_inputs,
        'parameters': _dedupe_parameters(parameters),
        'outputs': outputs,
        'dependencies': {
            'models': [{'name': model, 'required': True} for model in sorted(models)],
            'customNodes': list(custom_nodes.values()),
        },
        'nodeTypes': sorted(set(node_types)),
    }


def analyze_api_workflow(data: dict[str, Any], filename: str) -> dict[str, Any]:
    node_types = [str(node.get('class_type') or '') for node in data.values() if isinstance(node, dict)]
    name = _clean_name(filename)
    category, capabilities = _category_from_text(name, node_types)
    models: set[str] = set()
    custom_nodes: dict[str, dict[str, Any]] = {}
    outputs: list[dict[str, Any]] = []
    parameters: list[dict[str, Any]] = []

    for node_id, node in data.items():
        if not isinstance(node, dict):
            continue
        node_type = str(node.get('class_type') or '')
        inputs = node.get('inputs') or {}
        models.update(_extract_models_from_values(inputs))
        lower = node_type.lower()
        seed = inputs.get('seed')
        if 'sampler' in lower and isinstance(seed, int) and not isinstance(seed, bool):
            parameters.append({
                'key': 'seed',
                'label': 'Seed',
                'type': 'seed',
                'default': seed,
                'description': '控制随机采样；使用相同 Seed 有助于复现结果。',
                'mapping': {'nodeId': str(node_id), 'field': 'seed'},
            })
        if lower.startswith('pixaroma'):
            custom_nodes['ComfyUI-Pixaroma'] = {'name': 'ComfyUI-Pixaroma', 'required': True}
        if any(hint in lower for hint in OUTPUT_VIDEO_HINTS):
            outputs.append({'key': f'output_{node_id}', 'type': 'video', 'format': 'mp4', 'mapping': {'nodeId': str(node_id)}})
        elif any(hint in lower for hint in OUTPUT_IMAGE_HINTS):
            outputs.append({'key': f'output_{node_id}', 'type': 'image', 'format': 'png', 'mapping': {'nodeId': str(node_id)}})

    return {
        'format': 'api-workflow',
        'hash': canonical_hash(data),
        'name': name,
        'slug': _slug(name),
        'category': category,
        'capabilities': capabilities,
        'nodeCount': len(data),
        'linkCount': 0,
        'inputs': [],
        'parameters': _dedupe_parameters(parameters),
        'outputs': outputs or [{'key': 'output', 'type': 'video' if 'video' in category else 'image', 'mapping': {}}],
        'dependencies': {
            'models': [{'name': model, 'required': True} for model in sorted(models)],
            'customNodes': list(custom_nodes.values()),
        },
        'nodeTypes': sorted(set(node_types)),
    }


def analyze_workflow(data: dict[str, Any], filename: str) -> dict[str, Any]:
    workflow_format = detect_workflow_format(data)
    if workflow_format == 'ui-workflow':
        return analyze_ui_workflow(data, filename)
    if workflow_format == 'api-workflow':
        return analyze_api_workflow(data, filename)
    return {
        'format': 'resource-json',
        'hash': canonical_hash(data),
        'name': _clean_name(filename),
        'slug': _slug(_clean_name(filename)),
        'category': 'resource',
        'capabilities': [],
        'nodeCount': 0,
        'linkCount': 0,
        'inputs': [],
        'parameters': [],
        'outputs': [],
        'dependencies': {'models': [], 'customNodes': []},
        'nodeTypes': [],
    }


def _dedupe_parameters(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get('key'))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
