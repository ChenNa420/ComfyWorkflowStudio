# Phase 1G-2 · Execution-aware Remediation Guides

## 背景

Phase 1G-1 的 Readiness Planner 已经可以计算 `affectedCount` 与保守的 `unlockCount`，但真实验收暴露了一个重要事实：`MarkdownNote` 成为了最大 blocker，影响 92 个 Workflow、直接解锁 37 个。

这与 Runtime Converter 的实际行为不一致。Converter 明确不会执行：

- `Note`
- `MarkdownNote`
- `PixaromaNote`
- `PixaromaLabel`
- `mode = Never (2)` 的节点
- ComfyUI 不认识、同时又没有任何下游 output link 的 UI 辅助节点

因此 Phase 1G-2 先修正“什么才是真正的执行依赖”，然后再生成修复指南。

## 目标

1. Dependency Inventory 与 Runtime Converter 使用同一套执行语义。
2. 非执行 UI 节点不再进入 `MISSING_DEPENDENCIES`、Readiness blocker、Near Ready 和 unlockCount。
3. 对剩余真实 blocker 生成只读、证据化的修复指南。
4. 不自动下载模型，不自动安装 Custom Node，不修改 ComfyUI，不修改 Manifest。

## Execution-aware Node Rules

Dependency Inventory 优先读取 Workflow Package 中的 `original.json`：

- 已知 `NON_EXECUTION_NODE_TYPES`：忽略。
- `mode=2`：忽略。
- ComfyUI 当前不认识该节点，但节点没有任何 downstream output link：按照 Converter 语义视为 UI-only，忽略。
- 其他节点才进入 runtime dependency inventory。

如果缺少可解析的 `original.json`，才退回 `analysis.json -> nodeTypes`，同时仍忽略已知非执行节点。

API 会额外返回：

- `workflow.ignoredNodeTypes`
- `workflow.counts.ignoredNodeTypes`
- `summary.ignoredNodeTypes`
- `summary.ignoredNodeOccurrences`
- 根级 `ignoredNodeTypes`

这些信息只用于解释为什么某些节点不再阻塞运行。

## Remediation Guides

新增：

`GET /api/remediation-guides`

查询参数：

- `capability`
- `category`
- `limit`
- `forceRefresh`

每条 Guide 包含：

- `kind`: MODEL / NODE
- `name`
- `affectedCount`
- `unlockCount`
- `action`
- `confidence`
- `writeMode=false`
- `evidence`
- `safety`

### Custom Node Guide

只使用受影响 Workflow 的 Manifest 中已经声明的：

- `dependencies.customNodes[].name`
- `dependencies.customNodes[].installUrl`

系统会计算声明覆盖率：

- >= 80%：HIGH
- >= 40%：MEDIUM
- < 40%：LOW

即使是 HIGH，也只表示“Manifest 证据较一致”，不代表系统已经验证远端仓库一定提供该 node type。

如果 Manifest 没有证据，保持：

`MANUAL_REVIEW`

系统不会根据 `MarkdownNodeX`、`FooSampler` 这样的 nodeType 名称去猜 GitHub 仓库。

### Model Guide

只使用 Manifest 中该模型依赖已声明的：

- `path`
- `installUrl`

如果没有 path / installUrl，不猜 Hugging Face、Civitai、GitHub 或任何下载站，保持人工确认。

## UI

`#/readiness` 增加两个 Tab：

- 优先级计划
- 安全修复指南

安全修复指南展示：

- 可直接解锁数
- 影响 Workflow 数
- 证据等级
- Manifest 中声明的 Custom Node 包名 / URL
- Manifest 中声明的模型 path / URL
- 被排除的非执行节点数量

UI 没有安装、下载、Apply 或修改按钮。

## Offline Safety

ComfyUI 离线时：

- `guides=[]`
- `blocked=0`
- 不生成 install guidance
- UNKNOWN 不变成 MISSING

## 验收重点

Phase 1G-1 的真实 Top blocker 是 `MarkdownNote`。Phase 1G-2 验收时必须确认：

- `MarkdownNote` 不再出现在 `/api/readiness/plan -> topBlockers`。
- `Note` / `PixaromaNote` / `PixaromaLabel` 同样不作为运行 blocker。
- Dependency Inventory 的 READY/BLOCKED 数量应重新计算；数字变化是预期结果。
- 对至少 3 个真实 blocker 核对 Guide 证据来源。
- Guide 中的 URL / path 必须能追溯到对应 Manifest，不能是系统猜测。
- `writeMode=false`。
- 没有模型、Custom Node、Manifest、SQLite 或 Workflow Package 写入。
- Phase 1F / 1E Runtime safety 全量回归继续 PASS。

本地命令：

```powershell
cd D:\ComfyWorkflowStudio
python -m unittest discover -s tests -v
npm run build
python scripts\phase1g2_guides_smoke.py
```
