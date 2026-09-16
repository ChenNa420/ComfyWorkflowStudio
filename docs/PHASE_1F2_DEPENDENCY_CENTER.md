# Phase 1F-2 · Dependency Center + Manifest Review

## 目标

在 Phase 1F-1 工作流知识库之上增加两项能力：

1. 使用当前 ComfyUI `/object_info` 做真实依赖盘点。
2. 给 Manifest 提供“只补空字段、不覆盖人工内容”的安全审核建议。

本阶段不自动安装模型、不自动安装 Custom Node、不扫描用户任意目录，也不修改第三方 `original.json`。

## 真实依赖盘点

### 模型

系统从 Workflow Manifest 中读取声明模型，再从 ComfyUI `/object_info` 的节点输入枚举中收集当前 ComfyUI 已注册的模型文件。

匹配顺序：

1. 标准化路径后的精确匹配。
2. 唯一 basename 匹配。
3. basename 多匹配时标记为已存在但保留 alternatives 信息。
4. 未匹配则 `MISSING`。
5. ComfyUI 离线时必须 `UNKNOWN`，不能误报 `MISSING`。

这种方式只读，不遍历或修改 ComfyUI 模型目录。

### 节点

系统用每个 Package 的 `analysis.json -> nodeTypes` 与实时 `/object_info` key 比较。

- 存在：`PRESENT`
- 不存在：`MISSING`
- ComfyUI 离线：`UNKNOWN`

`PixaromaNote`、`PixaromaLabel` 等非执行说明节点从依赖判定中忽略。

### Custom Node 包

Manifest 的 `dependencies.customNodes` 是包级声明；实际能否执行以 Workflow 所需 nodeTypes 是否存在为准。

Phase 1F-2 不根据包名猜测安装状态。

### 快照缓存

依赖 Inventory 默认使用短时缓存，避免依赖中心多个并行请求重复拉取大型 `/object_info`。显式刷新时可通过 `forceRefresh=true` 重新获取当前 ComfyUI 快照。

## Dependency APIs

- `GET /api/dependencies/inventory`
- `GET /api/dependencies/summary`
- `GET /api/dependencies/workflows`
- `GET /api/dependencies/workflows/{workflowId}`
- `GET /api/dependencies/models`
- `GET /api/dependencies/nodes`

## Manifest 安全审核

API：

- `GET /api/manifest-review`
- `GET /api/manifest-review/{workflowId}`
- `POST /api/manifest-review/{workflowId}/apply-safe`

安全补全规则：

- 不覆盖已有人工字段。
- 不修改 `original.json`。
- `notRecommendedFor` 不自动生成。
- 输入语义、说明和 Mapping 只有 `analysisConfidence >= 0.80` 才允许作为安全建议。
- description / recommendedFor / guide 使用确定性的 category 默认值，只补空值或导入时的通用占位说明。
- Apply 必须由用户显式触发，不在扫描、启动或批量导入时自动执行。

## UI

`#/dependencies` 现在包含：

- 按工作流查看依赖状态。
- 模型依赖表。
- 节点类型表。
- Manifest 审核队列。
- 单 Workflow 依赖详情抽屉。
- Manifest 安全建议抽屉。
- 显式“安全补全”按钮。

## 本地验收

```powershell
cd D:\ComfyWorkflowStudio
python -m unittest discover -s tests -v
npm run build
python scripts\phase1f2_dependency_smoke.py
```

真实验收要求：

- ComfyUI 8188 在线。
- `/api/dependencies/summary` connected=true。
- 至少抽查 MiniMax H3、Wan、ControlNet、TTS 工作流依赖。
- 已安装节点不能误报缺失。
- 确实缺失节点应显示 MISSING。
- 模型匹配结果可追溯到 ComfyUI object_info 枚举。
- ComfyUI 停止时状态变 UNKNOWN/COMFY_OFFLINE，而不是批量 MISSING。
- Manifest Review 只展示建议时不修改任何文件。
- 本轮验收可以不点击 `apply-safe`；如需测试写入，只选一个明确可恢复/可验证的 Package，并先记录 manifest.json hash。
- `original.json` hash 必须完全不变。
- Phase 1E Binding / Runtime / UNKNOWN 安全行为无回归。

## 后续

Phase 1F-3 可继续做：

- 模型类型细分（checkpoint / diffusion model / VAE / CLIP / ControlNet / LoRA）。
- 工作流批量人工审核工作台。
- 已确认 Manifest 的版本历史和回滚。
- 真实依赖状态反哺 Workflow Knowledge Card Health。
