# Phase 1F · Workflow Knowledge Base

## 目标

Phase 1F 不改写 Phase 1D/1E 已验收的 Runtime、ComfyUI 提交、输出回收和 AiEnglishAnimation Binding 主链路。

本阶段把已经导入的真实 ComfyUI Workflow Package 升级为可理解、可搜索、可推荐、可执行的工作流知识库。

## 本轮范围（1F-1）

- 工作流专业分类：图片、视频、音频、3D 与具体 category。
- Knowledge Card：用途、适合/不适合、输入语义、参数、依赖、使用说明。
- Manifest 完整度：0–100 + A/B/C/D + 缺失项。
- Workflow Health：
  - `READY`
  - `NEEDS_ADAPTATION`
  - `MISSING_DEPENDENCIES`
  - `UNSUPPORTED`
- 模型族与能力特征标签，例如 MiniMax H3、Wan、LTX、ControlNet、首帧控制、多参考图、角色一致性。
- 搜索与筛选：关键词、category、capability、health、family。
- 推荐排序：Manifest 完整度 + Health + 历史任务成功率。
- 运行历史：runs、successRate、FAILED、UNKNOWN/NEEDS_REVIEW。
- 工作流库 UI 用真实知识卡替换旧的简单列表。
- Knowledge Card 可直接进入“创建任务”或“工作流适配”。

## API

### `GET /api/workflow-knowledge/stats`

返回：总数、平均完整度、Health 分布、category、capability、family。

### `GET /api/workflow-knowledge`

查询参数：

- `q`
- `category`
- `capability`
- `health`
- `family`
- `limit`

### `GET /api/workflow-knowledge/recommendations`

查询参数：

- `capability`
- `q`
- `category`
- `family`
- `readyOnly`
- `limit`

### `GET /api/workflow-knowledge/{workflowId}`

返回完整 Knowledge Card + Manifest + analysis.json。

## 完整度原则

完整度不是“节点越多分越高”。评分关注是否真正能被普通用户理解与执行：

- 工作流说明
- 适用与不适用场景
- 输入语义
- 必填输入 Node Mapping
- 参数说明和 Mapping
- 输出定义
- 模型 / Custom Node 依赖
- 使用步骤和 Prompt 技巧
- Runtime 安全策略

`NEEDS_ADAPTATION` 不代表工作流坏了，只表示当前 Manifest 还不足以安全一键运行。

## Health 原则

Phase 1F 的知识库 Health 是产品层状态，不替代 `/api/workflows/{id}/compatibility` 的真实 ComfyUI 节点检查。

- `READY`：Manifest 输入映射、输出和安全策略达到当前产品门槛。
- `NEEDS_ADAPTATION`：输入语义、Mapping 或说明不完整。
- `MISSING_DEPENDENCIES`：已知兼容状态明确缺失依赖。
- `UNSUPPORTED`：不是可执行 Workflow。

## 推荐原则

推荐分只用来排序，不自动执行：

1. Manifest 完整度
2. Health
3. 已有真实运行成功率
4. 是否有清楚的适用场景

UNKNOWN / NEEDS_REVIEW 仍遵循 Phase 1D/1E 安全原则，不得因为推荐系统自动重复提交。

## Windows 验收

在 `D:\ComfyWorkflowStudio`：

```powershell
python -m unittest discover -s tests -v
npm run build
```

启动 API 后：

```powershell
python scripts\phase1f_knowledge_smoke.py
```

真实 UI：

`http://127.0.0.1:5174/#/workflows`

重点检查：

- 236 个真实工作流（数量以本机当前 Library 为准）能进入知识库统计。
- 搜索不是 mock 数据。
- category / capability / health / family 筛选有效。
- Knowledge Card 的输入、参数、依赖来自真实 Manifest。
- Manifest 完整度和 Health 能区分已适配与待适配工作流。
- “使用工作流”进入创建任务页面。
- “继续适配”进入 Workflow Adapter。
- Phase 1E Binding、Runtime Clone、严格串行、UNKNOWN 安全规则无回归。
- 浏览器 console 无 error。

## 暂不进入 1F-1 的内容

- 不自动安装模型或 Custom Node。
- 不修改第三方原始 Workflow。
- 不自动生成虚假的输入语义。
- 不自动替用户 Apply 不确定的适配。
- 不 merge `main`。

后续 1F-2 再增加“真实依赖盘点 + 模型路径存在性 + Custom Node 实时状态 + 批量 Manifest 审核/修复”。
