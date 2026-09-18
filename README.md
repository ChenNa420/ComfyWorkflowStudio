# ComfyWorkflowStudio

本地优先的 ComfyUI 工作流知识库与童语动画生产平台。当前主线为 **GPT Director + WebMCP + ChatGPT Web Image**。

## 当前能力

- Workflow Knowledge、依赖检查、Readiness 与 Runtime Preflight
- Certified Production Run、串行任务、输出与素材管理
- 本地漫画扫描、页面预览、GPT Director Story/Shot/Episode
- WebMCP 将所选漫画页以 ImageContent 交给“童语工坊 · AI动画编剧导演”并接收 Story / Shots / Prompts
- “创建并开始 GPT 创作”会自动读取全部 selectedPages、上传真实漫画页、等待 GPT 返回严格 JSON，并经 WebMCP 自动写回 Studio
- 普通 Chrome/Edge 本地开发时通过 MCP-B 5.1.0 补齐 `document.modelContext`，并可桥接到 `127.0.0.1:9333` 的本地 MCP relay
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

它只启动 Studio API（8100）和 Web（5174），并检测 ComfyUI（8188）、ChatGPT Image CDP（9222）和 WebMCP Relay（9333）。不会自动启动或关闭 ComfyUI，也不使用 LM Studio。

## 普通浏览器 WebMCP

在本地 `127.0.0.1:5174` / `localhost:5174` 上，Studio 会尝试加载固定版本的 MCP-B 浏览器兼容层：

- `@mcp-b/global@5.1.0`
- `@mcp-b/webmcp-local-relay@5.1.0` browser embed

因此普通 Chrome/Edge 即使没有原生 WebMCP，`document.modelContext.registerTool` 也可以由 MCP-B polyfill 提供。Relay 只指向本机 `ws://127.0.0.1:9333`。

如需给标准 MCP Client 暴露当前浏览器标签页里的 Studio tools，使用：

```text
tools/webmcp/mcp-client-config.example.json
```

或在 Node.js 22+ 环境运行：

```bat
tools\webmcp\start-local-relay.cmd
```

Relay 只允许 `http://127.0.0.1:5174` 和 `http://localhost:5174`，没有使用 `origin=*`。详细说明见 `tools/webmcp/README.md`。

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


## 一键启动 / 关闭

启动整个工作台：

```bat
start-workbench.cmd
```

启动脚本会负责：

- Studio API：8100
- Studio Web：5174
- WebMCP Relay：9333
- ChatGPT 专用 CDP Chrome：9222（未运行时自动启动）
- ComfyUI：只检测，不自动启动、不自动关闭
- LM Studio：不使用

关闭本项目启动的服务：

```bat
stop-workbench.cmd
```

关闭脚本只会停止确认属于 ComfyWorkflowStudio 的 API、Web、WebMCP Relay 和专用 ChatGPT Chrome。它会检查进程命令行，遇到占用同端口的其他程序会跳过并告警，不会盲目按端口杀进程。

`stop-workbench.cmd` 不会关闭 ComfyUI，也不会操作 LM Studio。
