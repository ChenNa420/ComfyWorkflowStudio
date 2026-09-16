from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from backend.workflow.dependencies import dependency_inventory


def _model_key(item: dict[str, Any]) -> str:
    return f"model:{str(item.get('name') or '').casefold()}"


def _node_key(item: dict[str, Any]) -> str:
    return f"node:{str(item.get('nodeType') or '').casefold()}"


def _workflow_blockers(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for item in workflow.get('models') or []:
        if item.get('required') and item.get('status') == 'MISSING':
            blockers.append(
                {
                    'key': _model_key(item),
                    'kind': 'MODEL',
                    'name': item.get('name'),
                    'modelType': item.get('modelType') or 'other',
                    'modelTypes': item.get('modelTypes') or [item.get('modelType') or 'other'],
                }
            )
    for item in workflow.get('nodeTypes') or []:
        if item.get('status') == 'MISSING':
            blockers.append(
                {
                    'key': _node_key(item),
                    'kind': 'NODE',
                    'name': item.get('nodeType'),
                }
            )
    return blockers


def build_readiness_plan(
    inventory: dict[str, Any],
    *,
    capability: str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Turn dependency inventory into a read-only remediation plan.

    `unlockCount` is deliberately conservative: it counts only workflows for
    which the blocker is the *last* missing dependency. `affectedCount` shows
    the wider blast radius, but is never presented as guaranteed unlocks.
    """
    connected = bool(inventory.get('connected'))
    workflows = list(inventory.get('workflows') or [])
    if capability:
        workflows = [item for item in workflows if capability in (item.get('capabilities') or [])]
    if category:
        workflows = [item for item in workflows if item.get('category') == category]

    ready = [item for item in workflows if item.get('status') == 'READY']
    blocked = [item for item in workflows if item.get('status') == 'MISSING_DEPENDENCIES'] if connected else []

    workflow_rows: list[dict[str, Any]] = []
    blocker_usage: dict[str, dict[str, Any]] = {}
    single_blocker_usage: Counter[str] = Counter()

    for workflow in blocked:
        blockers = _workflow_blockers(workflow)
        if len(blockers) == 1:
            single_blocker_usage[blockers[0]['key']] += 1
        workflow_rows.append(
            {
                'workflowId': workflow.get('workflowId'),
                'name': workflow.get('name'),
                'category': workflow.get('category'),
                'capabilities': list(workflow.get('capabilities') or []),
                'blockerCount': len(blockers),
                'missingModels': sum(1 for item in blockers if item['kind'] == 'MODEL'),
                'missingNodes': sum(1 for item in blockers if item['kind'] == 'NODE'),
                'blockers': blockers,
                'nearReady': len(blockers) == 1,
            }
        )
        for blocker in blockers:
            row = blocker_usage.setdefault(
                blocker['key'],
                {
                    **blocker,
                    'workflowIds': [],
                    'workflows': [],
                    'categories': Counter(),
                    'capabilities': Counter(),
                },
            )
            row['workflowIds'].append(workflow.get('workflowId'))
            row['workflows'].append({'id': workflow.get('workflowId'), 'name': workflow.get('name')})
            row['categories'][str(workflow.get('category') or 'other')] += 1
            for cap in workflow.get('capabilities') or []:
                row['capabilities'][str(cap)] += 1

    blocker_rows: list[dict[str, Any]] = []
    for key, item in blocker_usage.items():
        affected = len(set(item['workflowIds']))
        unlock = int(single_blocker_usage.get(key, 0))
        blocker_rows.append(
            {
                'key': key,
                'kind': item['kind'],
                'name': item['name'],
                'modelType': item.get('modelType'),
                'modelTypes': item.get('modelTypes'),
                'affectedCount': affected,
                'unlockCount': unlock,
                'priorityScore': unlock * 100 + affected,
                'categories': [{'key': k, 'count': v} for k, v in item['categories'].most_common()],
                'capabilities': [{'key': k, 'count': v} for k, v in item['capabilities'].most_common()],
                'workflows': item['workflows'][:50],
            }
        )

    blocker_rows.sort(key=lambda item: (-item['unlockCount'], -item['affectedCount'], item['kind'], str(item['name']).casefold()))
    workflow_rows.sort(key=lambda item: (item['blockerCount'], item['name'].casefold()))
    model_blockers = [item for item in blocker_rows if item['kind'] == 'MODEL']
    node_blockers = [item for item in blocker_rows if item['kind'] == 'NODE']
    near_ready = [item for item in workflow_rows if item['nearReady']]

    return {
        'connected': connected,
        'comfyUiUrl': inventory.get('comfyUiUrl'),
        'error': inventory.get('error'),
        'filters': {'capability': capability, 'category': category},
        'summary': {
            'workflows': len(workflows),
            'ready': len(ready),
            'blocked': len(blocked),
            'nearReady': len(near_ready),
            'multiBlocker': sum(1 for item in workflow_rows if item['blockerCount'] > 1),
            'modelBlockers': len(model_blockers),
            'nodeBlockers': len(node_blockers),
            'topUnlockPotential': sum(item['unlockCount'] for item in blocker_rows[:10]),
        },
        'topBlockers': blocker_rows[: max(1, min(limit, 500))],
        'modelBlockers': model_blockers[: max(1, min(limit, 500))],
        'nodeBlockers': node_blockers[: max(1, min(limit, 500))],
        'nearReadyWorkflows': near_ready[: max(1, min(limit, 500))],
        'blockedWorkflows': workflow_rows[: max(1, min(limit, 500))],
    }


def readiness_plan(
    *,
    capability: str | None = None,
    category: str | None = None,
    limit: int = 100,
    force_refresh: bool = False,
) -> dict[str, Any]:
    inventory = dependency_inventory(force_refresh=force_refresh)
    return build_readiness_plan(inventory, capability=capability, category=category, limit=limit)
