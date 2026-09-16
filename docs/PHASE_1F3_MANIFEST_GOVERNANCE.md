# Phase 1F-3 · Model Types + Manifest Governance

## 目标

在 Phase 1F-1 工作流知识库与 Phase 1F-2 真实依赖盘点通过后，Phase 1F-3 增加三项治理能力：

1. 模型类型细分，而不仅仅显示“模型文件”。
2. 让真实依赖状态反哺 Workflow Knowledge Card Health。
3. 建立批量人工审核预览、Manifest 版本历史和显式回滚。

本阶段继续遵守：

- 不自动安装模型。
- 不自动安装 Custom Node。
- 不修改第三方 `original.json`。
- 不批量自动写 Manifest。
- UNKNOWN / NEEDS_REVIEW 不自动重试。
- 不 merge `main`。

## 模型类型

系统只根据 ComfyUI `/object_info` 暴露的真实模型枚举及字段语义分类，不遍历用户任意目录。

当前类型：

- `checkpoint`
- `diffusion-model`
- `vae`
- `text-encoder`
- `controlnet`
- `lora`
- `vision`
- `adapter`
- `upscaler`
- `audio`
- `other`

`GET /api/dependencies/models` 新增 `modelType` 过滤。

## Dependency-aware Workflow Health

Phase 1F-1 的 Health 原本主要来自 Manifest 完整度。

Phase 1F-3 中：

- 实时依赖为 `MISSING_DEPENDENCIES` 时，Knowledge Card Health 同步降为 `MISSING_DEPENDENCIES`。
- ComfyUI 离线时不把所有 Knowledge Card 误降为缺依赖；卡片保留 Manifest 层判断，同时返回 `dependencyStatus=COMFY_OFFLINE`。
- 推荐接口 `readyOnly=true` 不再推荐实时依赖缺失的 Workflow。

## 批量人工审核

新增：

`POST /api/manifest-review/batch-preview`

Body：

```json
{
  "workflowIds": ["workflow-a", "workflow-b"]
}
```

返回选中 Workflow 的安全建议、平均完整度和建议总数。

**Batch Preview 永远 `writeMode=false`。**

Phase 1F-3 故意不提供“一键批量 Apply”。真正写入仍必须逐 Workflow 显式确认。

## Manifest 版本历史

Manifest 每次真正写入时：

1. 首次写入前建立 baseline。
2. 保存写入前版本。
3. 写入新 Manifest。
4. 保存写入后版本。

版本历史存放在：

`storage/manifest-history/<workflow-package>/`

`storage/**` 已被 Git 忽略，因此版本历史不会污染第三方 Package 或 Git 仓库。

普通 GET 查询历史不创建文件、不修改 Manifest。

API：

- `GET /api/manifest-history/{workflowId}`
- `GET /api/manifest-history/{workflowId}/{versionId}`
- `POST /api/manifest-history/{workflowId}/{versionId}/rollback`

回滚规则：

- 必须显式 POST。
- 回滚前先保留当前 Manifest 版本。
- 回滚本身也写入版本历史。
- 同步更新 SQLite `workflows.manifest_json`。
- 永不修改 `original.json`。

## UI

`#/dependencies` 升级为治理中心：

- Workflow 依赖状态。
- 模型类型列表和筛选。
- Node 类型列表。
- Manifest 批量人工审核选择。
- 批量只读预览。
- 单 Workflow 安全补全。
- Manifest 版本历史。
- 显式回滚。

## 本地验收

```powershell
cd D:\ComfyWorkflowStudio
python -m unittest discover -s tests -v
npm run build
python scripts\phase1f3_governance_smoke.py
```

真实验收重点：

- Phase 1F-1 / 1F-2 全部回归通过。
- 模型类型至少能真实区分 checkpoint / VAE / ControlNet / LoRA / diffusion model 中本机实际存在的类别。
- Knowledge Health 的 `MISSING_DEPENDENCIES` 数量应与实时依赖状态产生合理关联。
- ComfyUI 离线时 Knowledge Card 不应批量误判为缺依赖。
- Batch Preview 不写 Manifest。
- 打开历史页面本身不创建版本文件。
- 选择一个测试用 Manifest 做显式安全补全后，应该产生 baseline/before/after 版本。
- 显式 rollback 后 Manifest 文件和 SQLite 同步恢复。
- rollback 后再次产生历史记录。
- `original.json` hash 全程不变。
- `storage/manifest-history` 不进入 Git。
