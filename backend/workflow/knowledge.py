from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from backend.db import Database
from backend.models import WorkflowManifest
from backend.workflow.manifest import discover_manifests

CATEGORY_META: dict[str, dict[str, str]] = {
    'text-to-image': {'label': '文生图', 'group': 'image'},
    'image-to-image': {'label': '图生图', 'group': 'image'},
    'image-edit': {'label': '图像编辑', 'group': 'image'},
    'controlnet': {'label': 'ControlNet 控制', 'group': 'image'},
    'image-to-video': {'label': '首帧 / 图片生视频', 'group': 'video'},
    'first-last-video': {'label': '首尾帧视频', 'group': 'video'},
    'text-to-video': {'label': '文生视频', 'group': 'video'},
    'tts': {'label': '语音合成', 'group': 'audio'},
    'audio': {'label': '音乐 / 音频', 'group': 'audio'},
    '3d': {'label': '3D 生成', 'group': '3d'},
    'other': {'label': '其他工作流', 'group': 'other'},
}

FAMILY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('MiniMax H3', ('minimax', 'h3')),
    ('Wan 2.x', ('wanvideo', 'wan 2', 'wan2', 'wan_')),
    ('LTX Video', ('ltx',)),
    ('Flux', ('flux',)),
    ('SDXL', ('sdxl',)),
    ('Qwen', ('qwen',)),
    ('Fish Speech', ('fishs2', 'fish speech', 'fishspeech')),
    ('ControlNet', ('controlnet', 'openpose', 'depth', 'lineart')),
    ('Trellis', ('trellis',)),
)

VIDEO_CAPABILITIES = {'image-to-video', 'first-last-video', 'text-to-video'}


def _load_analysis(manifest_path: Path) -> dict[str, Any]:
    path = manifest_path.parent / 'analysis.json'
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _db_workflow_rows(db: Database) -> dict[str, dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute('SELECT id, enabled, compatibility_status FROM workflows').fetchall()
    return {str(row['id']): dict(row) for row in rows}


def _runtime_metrics(db: Database) -> dict[str, dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT workflow_id,
                   COUNT(*) AS runs,
                   SUM(CASE WHEN status='SUCCEEDED' THEN 1 ELSE 0 END) AS succeeded,
                   SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) AS failed,
                   SUM(CASE WHEN status IN ('UNKNOWN','NEEDS_REVIEW') THEN 1 ELSE 0 END) AS uncertain,
                   MAX(created_at) AS last_used_at
            FROM generation_tasks
            GROUP BY workflow_id
            """
        ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        runs = int(row['runs'] or 0)
        succeeded = int(row['succeeded'] or 0)
        result[str(row['workflow_id'])] = {
            'runs': runs,
            'succeeded': succeeded,
            'failed': int(row['failed'] or 0),
            'uncertain': int(row['uncertain'] or 0),
            'successRate': round((succeeded / runs) * 100, 1) if runs else None,
            'lastUsedAt': row['last_used_at'],
        }
    return result


def _families(manifest: WorkflowManifest, analysis: dict[str, Any]) -> list[str]:
    haystack = ' '.join(
        [manifest.name, manifest.description, manifest.category]
        + list(manifest.capabilities)
        + [str(item) for item in analysis.get('nodeTypes') or []]
    ).lower()
    families: list[str] = []
    for label, tokens in FAMILY_RULES:
        if any(token in haystack for token in tokens):
            families.append(label)
    return families


def _traits(manifest: WorkflowManifest, analysis: dict[str, Any]) -> list[str]:
    traits: list[str] = []
    purposes = {item.purpose for item in manifest.inputs if item.purpose}
    if 'video-start-frame' in purposes:
        traits.append('首帧控制')
    if 'video-end-frame' in purposes:
        traits.append('尾帧控制')
    reference_count = sum(1 for item in manifest.inputs if item.type == 'image')
    if reference_count >= 2:
        traits.append('多参考图')
    if 'character-reference' in purposes:
        traits.append('角色一致性')
    if 'style-reference' in purposes:
        traits.append('风格参考')
    if 'pose' in purposes:
        traits.append('姿势控制')
    if 'depth' in purposes:
        traits.append('深度控制')
    if 'lineart' in purposes:
        traits.append('线稿控制')
    if 'mask' in purposes:
        traits.append('蒙版编辑')
    if manifest.runtime.durationPolicy == 'dynamic':
        traits.append('动态时长')
    if any(item.type == 'audio' for item in manifest.inputs):
        traits.append('音频输入')
    if any(item.type == 'audio' for item in manifest.outputs):
        traits.append('音频输出')
    node_text = ' '.join(str(item) for item in analysis.get('nodeTypes') or []).lower()
    if any(token in node_text for token in ('ipadapter', 'instantid', 'pulid', 'faceid')):
        traits.append('身份一致性')
    return list(dict.fromkeys(traits))


def manifest_completeness(manifest: WorkflowManifest, analysis: dict[str, Any]) -> dict[str, Any]:
    score = 0.0
    missing: list[str] = []

    description_ok = len(manifest.description.strip()) >= 18
    guide_ok = bool(manifest.guide.summary.strip()) and bool(manifest.guide.steps)
    if description_ok:
        score += 8
    else:
        missing.append('description')
    if manifest.recommendedFor:
        score += 4
    else:
        missing.append('recommendedFor')
    if manifest.notRecommendedFor:
        score += 3
    else:
        missing.append('notRecommendedFor')
    if guide_ok:
        score += 10
    else:
        missing.append('guide')
    if manifest.guide.promptTips or not any(cap in VIDEO_CAPABILITIES for cap in manifest.capabilities):
        score += 5
    else:
        missing.append('promptTips')

    required_inputs = [item for item in manifest.inputs if item.required]
    if manifest.inputs:
        semantic_ok = sum(1 for item in manifest.inputs if item.purpose and (item.description or item.help))
        mapped_ok = sum(1 for item in required_inputs if item.mapping.nodeId and item.mapping.field)
        score += 14 * (semantic_ok / len(manifest.inputs))
        score += 16 * (mapped_ok / max(1, len(required_inputs)))
        if semantic_ok < len(manifest.inputs):
            missing.append('input-semantics')
        if mapped_ok < len(required_inputs):
            missing.append('input-mappings')
    elif manifest.capabilities and manifest.capabilities != ['workflow']:
        missing.extend(['inputs', 'input-mappings'])

    if manifest.parameters:
        described = sum(1 for item in manifest.parameters if item.description)
        mapped = sum(1 for item in manifest.parameters if item.mapping.nodeId and item.mapping.field)
        score += 5 * (described / len(manifest.parameters))
        score += 5 * (mapped / len(manifest.parameters))
        if mapped < len(manifest.parameters):
            missing.append('parameter-mappings')
    else:
        score += 4

    if manifest.outputs:
        mapped_outputs = sum(1 for item in manifest.outputs if item.mapping.nodeId or analysis.get('format') == 'api-workflow')
        score += 8 + 4 * (mapped_outputs / len(manifest.outputs))
        if mapped_outputs < len(manifest.outputs):
            missing.append('output-mappings')
    else:
        missing.append('outputs')

    dependencies = len(manifest.dependencies.models) + len(manifest.dependencies.customNodes)
    if dependencies:
        score += 7
    elif analysis.get('nodeCount'):
        score += 3
        missing.append('dependencies')

    if manifest.runtime.executionMode == 'serial' and manifest.runtime.retryUnknown is False and manifest.runtime.preserveOriginalWorkflow:
        score += 10
    else:
        missing.append('runtime-safety')

    confidence_values = [
        float(item.get('analysisConfidence'))
        for item in analysis.get('inputs') or []
        if isinstance(item, dict) and isinstance(item.get('analysisConfidence'), (int, float))
    ]
    analysis_confidence = round(sum(confidence_values) / len(confidence_values) * 100, 1) if confidence_values else None

    final_score = max(0, min(100, round(score)))
    return {
        'score': final_score,
        'grade': 'A' if final_score >= 85 else 'B' if final_score >= 70 else 'C' if final_score >= 50 else 'D',
        'missing': list(dict.fromkeys(missing)),
        'analysisConfidence': analysis_confidence,
        'requiredInputs': len(required_inputs),
        'mappedRequiredInputs': sum(1 for item in required_inputs if item.mapping.nodeId and item.mapping.field),
    }


def workflow_health(
    manifest: WorkflowManifest,
    analysis: dict[str, Any],
    completeness: dict[str, Any],
    compatibility_status: str | None,
    dependency_status: str | None = None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    workflow_format = str(analysis.get('format') or '')
    if workflow_format == 'resource-json':
        return 'UNSUPPORTED', ['resource-json 不是可执行 Workflow']
    if dependency_status == 'MISSING_DEPENDENCIES':
        return 'MISSING_DEPENDENCIES', ['实时 ComfyUI 依赖盘点发现缺失模型或节点']
    if compatibility_status and 'MISSING' in compatibility_status.upper():
        return 'MISSING_DEPENDENCIES', [compatibility_status]

    if completeness['mappedRequiredInputs'] < completeness['requiredInputs']:
        reasons.append('必填输入尚未完成 Node 映射')
    if completeness['score'] < 70:
        reasons.append('Manifest 完整度不足 70')
    if not manifest.outputs:
        reasons.append('缺少输出定义')

    if reasons:
        return 'NEEDS_ADAPTATION', reasons
    return 'READY', ['输入语义、映射和运行安全规则已达到可执行门槛']


def _recommendation_score(card: dict[str, Any]) -> int:
    score = int(card['completeness']['score'] * 0.55)
    if card['health'] == 'READY':
        score += 25
    elif card['health'] == 'NEEDS_ADAPTATION':
        score += 8
    metrics = card['runtimeMetrics']
    if metrics['runs']:
        success_rate = metrics['successRate'] or 0
        score += min(15, round(success_rate * 0.15))
    if card['manifest']['recommendedFor']:
        score += 5
    return max(0, min(100, score))


def build_workflow_card(
    manifest_path: Path,
    manifest: WorkflowManifest,
    *,
    db_row: dict[str, Any] | None = None,
    runtime_metrics: dict[str, Any] | None = None,
    dependency_status: str | None = None,
) -> dict[str, Any]:
    analysis = _load_analysis(manifest_path)
    completeness = manifest_completeness(manifest, analysis)
    compatibility = str((db_row or {}).get('compatibility_status') or '') or None
    health, health_reasons = workflow_health(manifest, analysis, completeness, compatibility, dependency_status)
    meta = CATEGORY_META.get(manifest.category, {'label': manifest.category or '未分类', 'group': 'other'})
    metrics = runtime_metrics or {
        'runs': 0,
        'succeeded': 0,
        'failed': 0,
        'uncertain': 0,
        'successRate': None,
        'lastUsedAt': None,
    }
    card = {
        'id': manifest.workflowId,
        'name': manifest.name,
        'category': manifest.category,
        'categoryLabel': meta['label'],
        'categoryGroup': meta['group'],
        'description': manifest.description,
        'difficulty': manifest.difficulty,
        'capabilities': list(manifest.capabilities),
        'families': _families(manifest, analysis),
        'traits': _traits(manifest, analysis),
        'health': health,
        'healthReasons': health_reasons,
        'dependencyStatus': dependency_status,
        'compatibilityStatus': compatibility,
        'completeness': completeness,
        'runtimeMetrics': metrics,
        'format': analysis.get('format'),
        'nodeCount': analysis.get('nodeCount'),
        'modelCount': len(manifest.dependencies.models),
        'customNodeCount': len(manifest.dependencies.customNodes),
        'inputCount': len(manifest.inputs),
        'outputTypes': [item.type for item in manifest.outputs],
        'manifest': {
            'recommendedFor': list(manifest.recommendedFor),
            'notRecommendedFor': list(manifest.notRecommendedFor),
            'guideSummary': manifest.guide.summary,
        },
        '_search': '',
    }
    card['recommendationScore'] = _recommendation_score(card)
    card['_search'] = ' '.join(
        [
            card['name'],
            card['category'],
            card['categoryLabel'],
            card['description'],
            ' '.join(card['capabilities']),
            ' '.join(card['families']),
            ' '.join(card['traits']),
            ' '.join(card['manifest']['recommendedFor']),
            ' '.join(card['manifest']['notRecommendedFor']),
        ]
    ).lower()
    return card


def workflow_knowledge_cards(
    db: Database,
    *,
    dependency_statuses: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows = _db_workflow_rows(db)
    metrics = _runtime_metrics(db)
    dependency_statuses = dependency_statuses or {}
    result = [
        build_workflow_card(
            path,
            manifest,
            db_row=rows.get(manifest.workflowId),
            runtime_metrics=metrics.get(manifest.workflowId),
            dependency_status=dependency_statuses.get(manifest.workflowId),
        )
        for path, manifest in discover_manifests()
    ]
    for item in result:
        item.pop('_search', None)
    return result


def search_workflow_knowledge(
    db: Database,
    *,
    q: str = '',
    category: str | None = None,
    capability: str | None = None,
    health: str | None = None,
    family: str | None = None,
    limit: int = 500,
    dependency_statuses: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows = _db_workflow_rows(db)
    metrics = _runtime_metrics(db)
    dependency_statuses = dependency_statuses or {}
    cards: list[dict[str, Any]] = []
    query = q.strip().lower()
    for path, manifest in discover_manifests():
        card = build_workflow_card(
            path,
            manifest,
            db_row=rows.get(manifest.workflowId),
            runtime_metrics=metrics.get(manifest.workflowId),
            dependency_status=dependency_statuses.get(manifest.workflowId),
        )
        if category and card['category'] != category:
            continue
        if capability and capability not in card['capabilities']:
            continue
        if health and card['health'] != health:
            continue
        if family and family not in card['families']:
            continue
        if query and query not in card['_search']:
            continue
        card.pop('_search', None)
        cards.append(card)
    cards.sort(key=lambda item: (-item['recommendationScore'], -item['completeness']['score'], item['name'].lower()))
    return cards[: max(1, min(limit, 1000))]


def workflow_knowledge_stats(
    db: Database,
    *,
    dependency_statuses: dict[str, str] | None = None,
) -> dict[str, Any]:
    cards = workflow_knowledge_cards(db, dependency_statuses=dependency_statuses)
    health = Counter(item['health'] for item in cards)
    categories = Counter(item['category'] for item in cards)
    capabilities = Counter(cap for item in cards for cap in item['capabilities'])
    families = Counter(family for item in cards for family in item['families'])
    dependency_states = Counter(item.get('dependencyStatus') or 'NOT_CHECKED' for item in cards)
    average = round(sum(item['completeness']['score'] for item in cards) / len(cards), 1) if cards else 0.0
    return {
        'total': len(cards),
        'averageCompleteness': average,
        'ready': health.get('READY', 0),
        'needsAdaptation': health.get('NEEDS_ADAPTATION', 0),
        'missingDependencies': health.get('MISSING_DEPENDENCIES', 0),
        'unsupported': health.get('UNSUPPORTED', 0),
        'health': dict(sorted(health.items())),
        'dependencyStates': dict(sorted(dependency_states.items())),
        'categories': [
            {
                'key': key,
                'label': CATEGORY_META.get(key, {'label': key})['label'],
                'count': count,
            }
            for key, count in categories.most_common()
        ],
        'capabilities': [{'key': key, 'count': count} for key, count in capabilities.most_common()],
        'families': [{'key': key, 'count': count} for key, count in families.most_common()],
    }


def workflow_knowledge_detail(
    db: Database,
    workflow_id: str,
    *,
    dependency_status: str | None = None,
) -> dict[str, Any] | None:
    rows = _db_workflow_rows(db)
    metrics = _runtime_metrics(db)
    for path, manifest in discover_manifests():
        if manifest.workflowId != workflow_id:
            continue
        analysis = _load_analysis(path)
        card = build_workflow_card(
            path,
            manifest,
            db_row=rows.get(workflow_id),
            runtime_metrics=metrics.get(workflow_id),
            dependency_status=dependency_status,
        )
        card.pop('_search', None)
        return {
            **card,
            'manifest': manifest.model_dump(mode='json'),
            'analysis': analysis,
            'packagePath': str(path.parent),
        }
    return None
