from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.models import WorkflowManifest
from backend.workflow.dependencies import dependency_inventory
from backend.workflow.manifest import discover_manifests
from backend.workflow.readiness import readiness_plan


def _manifest_index() -> dict[str, tuple[Path, WorkflowManifest]]:
    return {manifest.workflowId: (path, manifest) for path, manifest in discover_manifests()}


def _candidate_node_packages(blocker_name: str, workflow_ids: list[str], manifests: dict[str, tuple[Path, WorkflowManifest]]) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter()
    evidence: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for workflow_id in workflow_ids:
        found = manifests.get(workflow_id)
        if not found:
            continue
        _, manifest = found
        for dependency in manifest.dependencies.customNodes:
            key = (dependency.name.strip(), (dependency.installUrl or '').strip())
            if not key[0]:
                continue
            counts[key] += 1
            evidence[key].append(workflow_id)

    total = max(1, len(workflow_ids))
    result: list[dict[str, Any]] = []
    for (name, install_url), count in counts.most_common():
        ratio = count / total
        confidence = 'HIGH' if ratio >= 0.8 else 'MEDIUM' if ratio >= 0.4 else 'LOW'
        result.append({
            'packageName': name,
            'installUrl': install_url or None,
            'evidenceCount': count,
            'workflowCount': len(workflow_ids),
            'coverage': round(ratio * 100, 1),
            'confidence': confidence,
            'workflowIds': evidence[(name, install_url)][:50],
            'reason': f'{count}/{len(workflow_ids)} 个受影响 Workflow 的 Manifest 声明了该 Custom Node 包。',
        })
    return result


def _candidate_model_locations(blocker_name: str, workflow_ids: list[str], manifests: dict[str, tuple[Path, WorkflowManifest]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    workflow_map: defaultdict[str, list[str]] = defaultdict(list)
    for workflow_id in workflow_ids:
        found = manifests.get(workflow_id)
        if not found:
            continue
        _, manifest = found
        for dependency in manifest.dependencies.models:
            if dependency.name != blocker_name:
                continue
            if dependency.path:
                normalized = dependency.path.replace('\\', '/').strip()
                if normalized:
                    counts[normalized] += 1
                    workflow_map[normalized].append(workflow_id)
    result = []
    for path, count in counts.most_common():
        result.append({
            'declaredPath': path,
            'evidenceCount': count,
            'workflowIds': workflow_map[path][:50],
        })
    return result


def _candidate_model_urls(blocker_name: str, workflow_ids: list[str], manifests: dict[str, tuple[Path, WorkflowManifest]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    workflow_map: defaultdict[str, list[str]] = defaultdict(list)
    for workflow_id in workflow_ids:
        found = manifests.get(workflow_id)
        if not found:
            continue
        _, manifest = found
        for dependency in manifest.dependencies.models:
            if dependency.name != blocker_name:
                continue
            if dependency.installUrl:
                url = dependency.installUrl.strip()
                if url:
                    counts[url] += 1
                    workflow_map[url].append(workflow_id)
    return [
        {
            'url': url,
            'evidenceCount': count,
            'workflowIds': workflow_map[url][:50],
            'source': 'manifest',
        }
        for url, count in counts.most_common()
    ]


def remediation_guides(*, capability: str | None = None, category: str | None = None, limit: int = 50, force_refresh: bool = False) -> dict[str, Any]:
    inventory = dependency_inventory(force_refresh=force_refresh)
    if not inventory.get('connected'):
        return {
            'connected': False,
            'blocked': 0,
            'guides': [],
            'summary': {'guides': 0, 'withHighConfidenceAction': 0, 'withSourceUrl': 0, 'withDeclaredPath': 0},
            'rules': [
                'ComfyUI 离线时不生成安装建议。',
                '所有建议只读，不自动下载、安装或修改 Manifest。',
            ],
        }

    plan = readiness_plan(capability=capability, category=category, limit=1000, force_refresh=False)
    manifests = _manifest_index()
    guides: list[dict[str, Any]] = []

    for blocker in plan.get('topBlockers') or []:
        workflow_ids = [item['workflowId'] for item in blocker.get('workflows') or []]
        guide: dict[str, Any] = {
            'kind': blocker['kind'],
            'name': blocker['name'],
            'modelType': blocker.get('modelType'),
            'affectedCount': blocker['affectedCount'],
            'unlockCount': blocker['unlockCount'],
            'priorityScore': blocker['priorityScore'],
            'capabilities': blocker.get('capabilities') or [],
            'categories': blocker.get('categories') or [],
            'workflowIds': workflow_ids,
            'writeMode': False,
            'action': 'MANUAL_REVIEW',
            'confidence': 'LOW',
            'evidence': [],
            'safety': [
                '不会自动下载或安装。',
                '不会修改 ComfyUI、Workflow original.json 或 Manifest。',
                '安装或下载前必须由用户核对来源、许可证、模型类型和目标目录。',
            ],
        }

        if blocker['kind'] == 'NODE':
            packages = _candidate_node_packages(blocker['name'], workflow_ids, manifests)
            guide['candidatePackages'] = packages
            if packages:
                top = packages[0]
                guide['confidence'] = top['confidence']
                guide['action'] = 'VERIFY_CUSTOM_NODE_PACKAGE'
                guide['evidence'].append(top['reason'])
                if top.get('installUrl'):
                    guide['sourceUrl'] = top['installUrl']
            else:
                guide['evidence'].append('受影响 Workflow 的 Manifest 未声明可可靠关联的 Custom Node 包。')
        else:
            paths = _candidate_model_locations(blocker['name'], workflow_ids, manifests)
            urls = _candidate_model_urls(blocker['name'], workflow_ids, manifests)
            guide['declaredPaths'] = paths
            guide['sourceUrls'] = urls
            if paths:
                guide['action'] = 'VERIFY_MODEL_FILE'
                guide['confidence'] = 'HIGH' if len(paths) == 1 else 'MEDIUM'
                guide['evidence'].append(f"Manifest 中存在 {len(paths)} 个声明路径候选。")
            if urls:
                guide['action'] = 'VERIFY_MODEL_SOURCE'
                guide['confidence'] = 'HIGH' if len(urls) == 1 else 'MEDIUM'
                guide['evidence'].append(f"Manifest 中存在 {len(urls)} 个下载来源候选。")
            if not paths and not urls:
                guide['evidence'].append('Manifest 未提供路径或来源 URL，需要人工确认模型来源。')

        guides.append(guide)

    guides.sort(key=lambda item: (-item['unlockCount'], -item['affectedCount'], item['name'].casefold()))
    selected = guides[: max(1, min(limit, 500))]
    return {
        'connected': True,
        'blocked': plan.get('summary', {}).get('blocked', 0),
        'criteria': {'capability': capability, 'category': category},
        'summary': {
            'guides': len(selected),
            'withHighConfidenceAction': sum(1 for item in selected if item['confidence'] == 'HIGH'),
            'withSourceUrl': sum(1 for item in selected if item.get('sourceUrl') or item.get('sourceUrls')),
            'withDeclaredPath': sum(1 for item in selected if item.get('declaredPaths')),
        },
        'guides': selected,
        'rules': [
            '建议完全来自现有 Manifest、Dependency Inventory 与 Readiness 数据。',
            '不根据节点名称猜 GitHub 仓库，不根据模型文件名猜下载站点。',
            '没有来源证据时必须保持 MANUAL_REVIEW。',
            '所有操作均为人工执行；本阶段没有安装/下载动作。',
        ],
    }
