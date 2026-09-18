# Phase 1A Foundation

## 目标

建立 ComfyWorkflowStudio 的第一层技术底座，让后续的工作流库、工作流说明、任务执行、作品库和童语工坊接入都基于统一协议开发。

## 当前范围

- Vue 3 + Vite 前端壳
- FastAPI 本地 API
- SQLite 数据库骨架
- Workflow Manifest V1
- Workflow / Binding / GenerationTask / Output / Material 数据结构
- 工作流包目录约定
- 示例 MiniMax H3 I2V Manifest

## 端口

- Frontend: `5174`
- API: `8100`
- ComfyUI: 默认计划连接 `8188`

## 关键架构原则

1. 原始 Workflow 永远只读。
2. 执行时创建 Runtime Clone 后再注入参数。
3. 普通用户看到“首帧 / 尾帧 / Prompt / 时长”等业务字段，不直接接触 Node ID。
4. `UNKNOWN` / 提交结果不确定时禁止自动重复提交。
5. Workflow Package 不只是 JSON，还必须包含 Manifest、说明、依赖和示例。
6. 童语工坊通过 WorkflowBinding 选择工作流，优先级为 `SHOT > EPISODE > SYSTEM`。

## Workflow Package

```text
workflows/<workflow-id>/
├─ original.json
├─ workflow-api.json
├─ manifest.json
├─ README.md
├─ cover.webp
└─ examples/
```

## Phase 1B 入口

下一阶段实现：

1. 导入 ComfyUI API Workflow JSON
2. 自动分析节点 / 输入 / 输出
3. 工作流适配向导
4. 模型与 Custom Node 依赖检查
5. 创建任务动态表单
6. Runtime Clone + `/prompt` 提交
7. `/history` 确认与输出取回
8. 作品库
