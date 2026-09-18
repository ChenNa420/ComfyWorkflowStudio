# ComfyWorkflowStudio

本地优先的 ComfyUI 工作流知识库与童语动画生产平台。当前主线为 **GPT Director + WebMCP + ChatGPT Web Image**。

## 当前能力

- Workflow Knowledge、依赖检查、Readiness 与 Runtime Preflight
- Certified Production Run、串行任务、输出与素材管理
- 本地漫画扫描、页面预览、GPT Director Story/Shot/Episode
- WebMCP 将所选漫画页以 ImageContent 交给“童语工坊 · AI动画编剧导演”并接收 Story / Shots / Prompts
- ChatGPT Web Image Worker 通过本地 Chrome CDP 生成 Shot 关键帧并回填到 Studio
- ComfyUI 继续负责后续工作流执行；图片引擎不依赖 OpenAI API Key

## 本地服务

- Web：`http://127.0.0.1:5174`
- API：`http://127.0.0.1:8100`
- ComfyUI：默认 `http://127.0.0.1:8188`

## 一键启动

Windows：

```bat
start-workbench.cmd
```

它只启动 Studio API（8100）和 Web（5174），并检测 ComfyUI（8188）和 ChatGPT Image CDP（9222）。不会启动或关闭 ComfyUI，也不使用 LM Studio。

## GPT Director / 童语工坊 GPT

默认 GPT：

`https://chatgpt.com/g/g-6aa62443216c819181e35cd36d02e486-tong-yu-gong-fang-aidong-hua-bian-ju-dao-yan`

故事主链：

```text
Selected comic pages
→ WebMCP ImageContent
→ 童语工坊 GPT
→ Story / Shots / Prompts
→ WebMCP
→ ComfyWorkflowStudio
```

关键帧主链：

```text
Shot.imagePrompt
→ local Chrome CDP
→ 童语工坊 GPT
→ generated image
→ local frame storage
→ Shot preview
```

首次使用图片引擎：

```bat
tools\chatgpt-image\start-cdp-chrome.cmd
```

保持该 Chrome 窗口开启并登录 ChatGPT。Worker 默认连接 `http://127.0.0.1:9222`，无需 OpenAI API Key。

历史 Local AI / LM Studio 代码仅保留用于旧阶段兼容和回归测试，不属于当前默认运行依赖。

## 验证

```powershell
python -m unittest discover -s tests -v
npm run typecheck
npm run build
```
