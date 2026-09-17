# ComfyWorkflowStudio

本地优先的 ComfyUI 工作流知识库与童语动画生产平台。当前阶段为 **Phase 1H-4**。

## 当前能力

- Workflow Knowledge、依赖检查、Readiness 与 Runtime Preflight
- Certified Production Run、串行任务、输出与素材管理
- 本地漫画扫描、页面预览、Comic-to-Story Episode
- 可插拔 AI Semantic Provider，支持证据页、故事改编和严格 Episode Schema

## 本地服务

- Web：`http://127.0.0.1:5174`
- API：`http://127.0.0.1:8100`
- ComfyUI：默认 `http://127.0.0.1:8188`

## Comic AI Provider

默认 `COMIC_AI_PROVIDER=disabled`，只做本地解析，**不会自动把漫画发送到网络**。

本地 OpenAI-compatible Vision 服务示例：

```powershell
$env:COMIC_AI_PROVIDER="openai_compatible"
$env:COMIC_AI_BASE_URL="http://127.0.0.1:1234/v1"
$env:COMIC_AI_MODEL="local-vision-model"
```

本地无认证服务可以不设置 `COMIC_AI_API_KEY`。非 localhost 地址默认拒绝，只有显式设置 `COMIC_AI_ALLOW_REMOTE=true` 才允许连接。结构化输出默认为 `json_object`，也可设置 `COMIC_AI_STRUCTURED_OUTPUT=json_schema`。

## 验证

```powershell
python -m unittest discover -s tests -v
npm run typecheck
npm run build
```
