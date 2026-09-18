# Workflow Manifest V1

`manifest.json` 是 ComfyWorkflowStudio 理解一套 ComfyUI Workflow 的核心协议。它描述“这套工作流是做什么的、需要什么输入、参数怎么填、依赖什么、输出什么、普通用户应该怎么使用”。

## 顶层字段

- `schemaVersion`: 当前固定 `1.0`
- `workflowId`: 稳定唯一 ID
- `name`: 展示名称
- `category`: 如 `image-to-video`
- `description`: 一句话用途
- `difficulty`: `easy | medium | advanced`
- `source`: 来源信息
- `capabilities`: 能力标签
- `recommendedFor`: 推荐用途
- `notRecommendedFor`: 不推荐用途
- `inputs`: 输入素材/文本
- `parameters`: 可调参数
- `outputs`: 输出定义
- `dependencies`: 模型与自定义节点依赖
- `runtime`: 执行策略
- `guide`: 使用教程

## 输入 purpose

第一版约定：

- `video-start-frame`
- `video-end-frame`
- `source-image`
- `character-reference`
- `scene-reference`
- `style-reference`
- `pose`
- `depth`
- `lineart`
- `mask`
- `control-image`
- `prompt`
- `negative-prompt`
- `other`

这些 purpose 让童语工坊能够判断某工作流到底需要“首帧”“尾帧”“角色参考图”还是其他素材。

## Mapping

普通用户不需要知道 Node ID，但适配器需要把业务字段映射到 ComfyUI API Workflow：

```json
{
  "mapping": {
    "nodeId": "21",
    "field": "image"
  }
}
```

动态策略可以使用：

```json
{
  "mapping": {
    "strategy": "duration-to-frames"
  }
}
```

## Runtime 安全原则

```json
{
  "executionMode": "serial",
  "durationPolicy": "dynamic",
  "allowRetry": true,
  "retryUnknown": false,
  "preserveOriginalWorkflow": true,
  "outputTimeout": 900
}
```

`retryUnknown` 默认必须为 `false`。如果一次 `/prompt` 提交结果不确定，不允许系统自动再次提交。

## WorkflowBinding

童语工坊选择工作流时使用三级覆盖：

```text
SHOT > EPISODE > SYSTEM
```

例如 EP003 默认使用 MiniMax H3，但 Shot04 可以单独切换为 Wan 2.2。
