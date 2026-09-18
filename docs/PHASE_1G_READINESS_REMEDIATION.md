# Phase 1G · Workflow Readiness Remediation

## 背景

Phase 1F-3 真实验收结果：

- Workflow 总数：228
- Dependency READY：56
- MISSING_DEPENDENCIES：172
- Workflow Knowledge READY：38
- NEEDS_ADAPTATION：18

Phase 1G 不再继续堆底层框架，目标转为：**提高真实可运行率**。

第一步不是自动安装，而是把 172 个缺依赖工作流拆成“最值得先解决的具体阻塞项”。

## Phase 1G-1 · Readiness Remediation Planner

新增只读修复计划：

- 缺失模型按文件名聚合。
- 缺失节点按 nodeType 聚合。
- 统计每个阻塞项影响多少 Workflow。
- 统计每个阻塞项能保守直接解锁多少 Workflow。
- 找出 `blockerCount = 1` 的 Near Ready Workflow。
- 支持按 capability / category 聚焦，例如只看 `image-to-video`。

### 两个数字不能混淆

`affectedCount`：这个缺失依赖出现在多少个阻塞 Workflow 中。

`unlockCount`：当前**只有这一项缺失**的 Workflow 数量。

`unlockCount` 才可以被描述为“解决这一项后可直接解锁”。系统不会把“影响 20 个”说成“安装后一定解锁 20 个”。

## API

### `GET /api/readiness/plan`

参数：

- `capability`
- `category`
- `limit`
- `forceRefresh`

返回：

- summary
- topBlockers
- modelBlockers
- nodeBlockers
- nearReadyWorkflows
- blockedWorkflows

### `GET /api/readiness/near-ready`

只返回当前只差一个依赖的 Workflow。

## 离线安全

ComfyUI 离线时：

- `connected=false`
- 不生成缺失模型 / 缺失节点修复建议
- `blocked=0`
- blocker list 为空

因为离线时依赖状态是 UNKNOWN，不能把 UNKNOWN 误当 MISSING。

## UI

地址：

`http://127.0.0.1:5174/#/readiness`

页面展示：

- 当前 READY
- 缺依赖 Workflow
- 只差 1 个依赖的 Near Ready Workflow
- Top 10 保守解锁潜力
- 优先阻塞项
- 模型 / 节点筛选
- capability 筛选
- Near Ready Workflow 列表

Phase 1G-1 不提供安装按钮。

## 安全边界

本阶段：

- 不下载模型。
- 不安装 Custom Node。
- 不修改 ComfyUI。
- 不写 Manifest。
- 不修改 `original.json`。
- 不提交生成任务。
- 不改变 Phase 1E 串行 / UNKNOWN 安全规则。
- 不 merge `main`。

## Windows 本地验收

```powershell
cd D:\ComfyWorkflowStudio
python -m unittest discover -s tests -v
npm run build
python scripts\phase1g_readiness_smoke.py
```

重点验证：

1. Phase 1F-1/2/3 与 Phase 1E 全量回归。
2. `/api/health phase=1G`。
3. 真实 228 个 Workflow 进入 Readiness Planner。
4. `ready + blocked` 与实时 Dependency Inventory 在在线状态下合理一致。
5. Top blocker 的 `affectedCount` 可从真实 Workflow 反查。
6. Top blocker 的 `unlockCount` 只统计 blockerCount=1 的 Workflow。
7. `image-to-video` capability 聚焦结果正确。
8. ComfyUI 离线后修复列表清空，不误报缺依赖。
9. `#/readiness` 浏览器 Console 无 error/warning。
10. 不产生任何模型下载、Node 安装、Manifest 写入或 Git 污染。

## 后续 Phase 1G-2

Phase 1G-1 真实数据回来以后，再决定最值钱的方向：

- 如果主要瓶颈是少数 Custom Node：做“节点包识别 + 安装说明映射”，仍不自动安装。
- 如果主要瓶颈是少数共享模型：做“模型依赖规格卡 + 本地路径确认 + 下载来源记录”，下载仍需显式操作。
- 如果 Near Ready 很多：优先把最小成本依赖补齐，提高 READY 数量。
- 如果多数 Workflow 同时缺 3–10 项依赖：先做工作流分级和目标能力集，不追求 228 个全部可运行。
