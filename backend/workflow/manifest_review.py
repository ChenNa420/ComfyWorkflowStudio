from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.db import Database
from backend.models import WorkflowManifest
from backend.workflow.knowledge import manifest_completeness
from backend.workflow.manifest import discover_manifests, save_manifest

CATEGORY_DESCRIPTION = {
    'image-to-video': '使用一张或多张图片作为条件生成视频。',
    'first-last-video': '使用首帧与尾帧控制视频起止状态。',
    'text-to-video': '根据文本提示生成视频。',
    'text-to-image': '根据文本提示生成图片。',
    'image-edit': '对输入图片进行编辑或重绘。',
    'controlnet': '使用 Pose、Depth、Lineart 等控制条件生成图片或视频。',
    'tts': '把文本转换为语音。',
    'audio': '生成或处理音乐与音频。',
    '3d': '根据图片或文本生成 3D 相关结果。',
}

CATEGORY_RECOMMENDED = {
    'image-to-video': ['动画镜头', '人物或动物动作', '短视频'],
    'first-last-video': ['首尾状态控制', '镜头衔接', '短视频'],
    'text-to-video': ['概念视频', '无首帧素材的镜头'],
    'text-to-image': ['首帧', '角色图', '场景图'],
    'image-edit': ['局部重绘', '画面修复', '素材编辑'],
    'controlnet': ['姿势控制', '构图控制', '结构约束'],
    'tts': ['配音', '对白生成'],
    'audio': ['音乐', '音效', '音频处理'],
    '3d': ['3D 素材', '模型生成'],
}


def _load_analysis(path: Path) -> dict[str, Any]:
    target = path.parent / 'analysis.json'
    if not target.is_file():
        return {}
    try:
        value = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_input_proposals(manifest: WorkflowManifest, analysis: dict[str, Any]) -> list[dict[str, Any]]:
    by_key = {
        str(item.get('key')): item
        for item in analysis.get('inputs') or []
        if isinstance(item, dict) and item.get('key')
    }
    proposals: list[dict[str, Any]] = []
    for current in manifest.inputs:
        source = by_key.get(current.key)
        if not source:
            continue
        confidence = float(source.get('analysisConfidence') or 0)
        if confidence < 0.80:
            continue
        changes: dict[str, Any] = {}
        if not current.purpose and source.get('purpose'):
            changes['purpose'] = source['purpose']
        if not current.description.strip() and source.get('description'):
            changes['description'] = source['description']
        if not current.help.strip() and source.get('help'):
            changes['help'] = source['help']
        mapping = current.mapping.model_dump(mode='json')
        source_mapping = source.get('mapping') if isinstance(source.get('mapping'), dict) else {}
        if not mapping.get('nodeId') and source_mapping.get('nodeId'):
            changes['mapping.nodeId'] = str(source_mapping['nodeId'])
        if not mapping.get('field') and source_mapping.get('field'):
            changes['mapping.field'] = str(source_mapping['field'])
        if changes:
            proposals.append({
                'type': 'input',
                'key': current.key,
                'confidence': round(confidence, 3),
                'changes': changes,
                'source': 'analysis.json',
            })
    return proposals


def manifest_review_item(path: Path, manifest: WorkflowManifest) -> dict[str, Any]:
    analysis = _load_analysis(path)
    completeness = manifest_completeness(manifest, analysis)
    proposals: list[dict[str, Any]] = []

    generic_description = '从 ComfyUI 导入的工作流，等待补充完整使用说明。'
    if not manifest.description.strip() or manifest.description.strip() == generic_description:
        suggested = CATEGORY_DESCRIPTION.get(manifest.category)
        if suggested:
            proposals.append({'type': 'field', 'field': 'description', 'value': suggested, 'source': 'category-default'})
    if not manifest.recommendedFor:
        suggested = CATEGORY_RECOMMENDED.get(manifest.category)
        if suggested:
            proposals.append({'type': 'field', 'field': 'recommendedFor', 'value': suggested, 'source': 'category-default'})
    if not manifest.guide.summary.strip():
        summary = manifest.description.strip() or CATEGORY_DESCRIPTION.get(manifest.category, '')
        if summary:
            proposals.append({'type': 'field', 'field': 'guide.summary', 'value': summary, 'source': 'manifest'})
    if not manifest.guide.steps:
        steps = [f'准备 {item.label}' for item in manifest.inputs if item.required]
        steps.append('确认参数后提交任务')
        proposals.append({'type': 'field', 'field': 'guide.steps', 'value': steps, 'source': 'manifest'})
    if not manifest.guide.promptTips and 'video' in manifest.category:
        proposals.append({
            'type': 'field',
            'field': 'guide.promptTips',
            'value': ['明确主体动作', '描述环境变化', '需要时说明摄影机运动'],
            'source': 'category-default',
        })

    proposals.extend(_safe_input_proposals(manifest, analysis))
    return {
        'workflowId': manifest.workflowId,
        'name': manifest.name,
        'category': manifest.category,
        'completeness': completeness,
        'proposalCount': len(proposals),
        'proposals': proposals,
        'safeApplyOnly': True,
        'rules': [
            '不覆盖已有人工字段',
            '输入语义只接受 analysisConfidence >= 0.80 的分析结果',
            '不自动填写 notRecommendedFor',
            '不修改 original.json',
        ],
    }


def manifest_review_queue() -> list[dict[str, Any]]:
    items = [manifest_review_item(path, manifest) for path, manifest in discover_manifests()]
    items.sort(key=lambda item: (item['completeness']['score'], -item['proposalCount'], item['name'].casefold()))
    return items


def _set_nested(payload: dict[str, Any], field: str, value: Any) -> None:
    current = payload
    parts = field.split('.')
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def apply_safe_manifest_review(db: Database, workflow_id: str) -> dict[str, Any] | None:
    for path, manifest in discover_manifests():
        if manifest.workflowId != workflow_id:
            continue
        review = manifest_review_item(path, manifest)
        if not review['proposals']:
            return {'workflowId': workflow_id, 'applied': 0, 'manifest': manifest.model_dump(mode='json'), 'review': review}

        payload = deepcopy(manifest.model_dump(mode='json'))
        input_by_key = {str(item.get('key')): item for item in payload.get('inputs') or []}
        applied = 0
        for proposal in review['proposals']:
            if proposal['type'] == 'field':
                _set_nested(payload, proposal['field'], proposal['value'])
                applied += 1
                continue
            if proposal['type'] != 'input':
                continue
            target = input_by_key.get(proposal['key'])
            if not target:
                continue
            for field, value in proposal['changes'].items():
                if field == 'mapping.nodeId':
                    target.setdefault('mapping', {})['nodeId'] = value
                elif field == 'mapping.field':
                    target.setdefault('mapping', {})['field'] = value
                else:
                    target[field] = value
            applied += 1

        updated = WorkflowManifest.model_validate(payload)
        save_manifest(updated, path)
        with db.connect() as conn:
            conn.execute(
                """
                UPDATE workflows
                SET name=?, category=?, description=?, difficulty=?, manifest_json=?, updated_at=datetime('now')
                WHERE id=?
                """,
                (
                    updated.name,
                    updated.category,
                    updated.description,
                    updated.difficulty,
                    json.dumps(updated.model_dump(mode='json'), ensure_ascii=False),
                    workflow_id,
                ),
            )
        return {
            'workflowId': workflow_id,
            'applied': applied,
            'manifest': updated.model_dump(mode='json'),
            'review': manifest_review_item(path, updated),
        }
    return None
