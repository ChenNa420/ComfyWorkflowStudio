# Phase 1G-3 · Runtime Preflight Certification

## 背景

Phase 1G-2 将非执行 UI 节点从真实依赖中排除后，本机依赖 READY 从 56 提升到 102，BLOCKED 从 172 降到 126；`image-to-video` 从 6 READY 提升到 14 READY。

但是“依赖齐全”仍然不等于“这个 Workflow 可以安全进入真实生成”。在提交 GPU 任务之前，还需要验证：

- UI Workflow 能否被当前 Runtime Converter 转为 API Prompt；
- Manifest 的必填输入 Node/Field Mapping 是否仍然有效；
- 参数映射是否指向真实 Runtime Node；
- 输出节点是否可以确认；
- Runtime 安全规则是否仍然满足；
- 当前 ComfyUI object_info 与 Workflow 结构是否一致。

因此 Phase 1G-3 增加一个**完全只读、不提交 Prompt 的 Runtime Preflight Certification**。

## 状态

### `CERTIFIED`

同时满足：

- Dependency Inventory = `READY`；
- Workflow JSON 可以读取；
- UI Workflow 可以通过当前 `ui_workflow_to_prompt()`；
- required inputs 都有 Node/Field Mapping；
- Mapping 指向 Runtime Prompt 中存在的 Node/Field；
- 输出 Node 可以通过 Manifest Mapping 或 ComfyUI `output_node` 确认；
- `retryUnknown=false`；
- `preserveOriginalWorkflow=true`。

`CERTIFIED` 只代表**静态/Runtime 结构预检通过**，绝不表示已经真实生成成功。

### `NEEDS_REVIEW`

典型原因：

- UI→API 转换失败；
- required input mapping 缺失；
- Mapping 指向不存在的 Node/Field；
- 输出 Node 无法确认；
- 关键 Runtime 安全规则失效。

### `BLOCKED_DEPENDENCIES`

真实模型 / Custom Node 执行依赖尚未满足，因此不进入转换认证。

### `COMFY_OFFLINE`

ComfyUI 离线时不发放认证，避免用未知环境生成假 PASS。

## API

Phase 1G-3 复用 Readiness API：

```text
GET /api/readiness/preflight
GET /api/readiness/preflight/{workflowId}
```

列表参数：

- `capability`
- `category`
- `certifiedOnly`
- `forceRefresh`
- `limit`

返回 summary：

- workflows
- certified
- needsReview
- blockedDependencies
- offline
- errorCodes
- warningCodes

每个 Workflow 返回：

- dependencyStatus
- status
- sourceFormat
- sourcePath
- promptNodes
- detectedOutputNodes
- errors
- warnings
- `writeMode=false`
- `submitsPrompt=false`

## 明确不做

Phase 1G-3 不：

- 创建 Generation Task；
- 调用 `/prompt`；
- 上传首帧或其他素材；
- 运行 GPU 生成；
- 修改 Manifest；
- 修改 original.json；
- 安装模型；
- 安装 Custom Node；
- 写入 Manifest History。

## UI

`#/readiness` 顶层新增：

- 依赖治理
- Runtime 预检认证

预检页面显示：

- CERTIFIED 数量
- NEEDS_REVIEW 数量
- BLOCKED_DEPENDENCIES 数量
- 主要错误码
- 每个 Workflow 的 Runtime Node 数、输出节点、错误和提醒

页面明确写明：

> CERTIFIED ≠ 已真实生成成功。

## 建议验收顺序

1. 全量 228 Workflow 静态预检。
2. 对 102 个 Dependency READY Workflow 检查：
   - CERTIFIED 数量；
   - NEEDS_REVIEW 数量；
   - Top error codes。
3. 聚焦 `image-to-video`：Phase 1G-2 有 14 个依赖 READY，确认其中多少真正通过 Runtime Preflight。
4. 随机抽查 CERTIFIED、NEEDS_REVIEW、BLOCKED_DEPENDENCIES 各 3 个。
5. 确认 API 调用前后 generation_tasks 数量完全不变。
6. 确认 ComfyUI queue/history 没有新增任务。
7. ComfyUI 离线时所有本轮项目只能进入 `COMFY_OFFLINE`，不能产生 CERTIFIED。

## 下一阶段

只有 Phase 1G-3 PASS 后，才进入 Phase 1G-4：

**小样本 Real Execution Certification**。

那一步也不会一次跑 102 个 Workflow，而是优先选择：

- `image-to-video` 中的 CERTIFIED Workflow；
- 已有本机模型；
- 输入简单；
- 运行成本较低；
- 已有历史成功记录的 Workflow。

每种能力先跑 1–3 个，逐步建立“静态预检 → 真实运行认证”的证据链。
