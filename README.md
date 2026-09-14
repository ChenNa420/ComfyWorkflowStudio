# ComfyWorkflowStudio

ComfyUI 工作流知识库 + 一键生成平台。

目标：把 ComfyUI Workflow 从“一个 JSON 文件”升级为可理解、可配置、可复用、可执行的 Workflow App Package，并提供给童语工坊（AiEnglishAnimation）和其他创作项目复用。

## 当前开发阶段

`feat/phase1b-1d` 已进入 Phase 1D 候选实现：

- Phase 1B：统一产品 UI、童语工坊页面、成片工作台、工作流库与任务页面
- Phase 1C：JSON / ZIP 批量导入、UI/API Workflow 识别、节点分析、输入用途推断、模型/Custom Node 提取、Hash 去重、Manifest 草稿
- Phase 1D：Runtime Clone、UI Workflow → API Prompt 转换、素材上传、ComfyUI `/prompt`、`/history` 确认、串行安全任务队列、输出回收与作品库

## 本地地址

- Web: `http://127.0.0.1:5174`
- API: `http://127.0.0.1:8100`
- ComfyUI: 默认 `http://127.0.0.1:8188`

可通过环境变量 `COMFYUI_URL` 修改 ComfyUI 地址。

## 安全原则

1. 第三方原始 Workflow 只读保存。
2. 导入的第三方工作流保存在 `storage/workflow-packages`，不进入 Git。
3. 每次生成创建 Runtime Clone，再注入输入和参数。
4. 执行队列默认串行。
5. 提交后状态不确定时标记 `UNKNOWN` / `NEEDS_REVIEW`，禁止自动重复提交。
6. 成功任务不会因为重试逻辑被无条件重新生成。

## 当前需要本地验收

Phase 1D 代码已经落入开发分支，但仍需要在用户 Windows + 实际 ComfyUI 环境中执行：

```powershell
python -m unittest discover -s tests -v
npm run build
```

然后用真实 MiniMax H3 首帧工作流完成第一条端到端生成，作为 Phase 1D 最终验收。
