# ComfyWorkflowStudio ChatGPT Image Worker

Local browser automation used by ComfyWorkflowStudio to generate one GPT Director shot keyframe at a time through a dedicated ChatGPT web browser profile.

The implementation is inspired by the architecture of `leixyou/chatgpt-web-image-mcp` (MIT). See `THIRD_PARTY_NOTICES.md`.

## Setup

```powershell
cd D:\ComfyWorkflowStudio\tools\chatgpt-image
npm install
node worker.js login
```

A dedicated browser window opens. Sign in to ChatGPT normally. Passwords, MFA codes and cookies are never read by ComfyWorkflowStudio; the browser profile stores the normal signed-in session locally under `storage/chatgpt-image-browser/profile`.

Check readiness:

```powershell
node worker.js check
```

If Chrome is unavailable but Microsoft Edge is installed:

```powershell
$env:CWS_CHATGPT_IMAGE_CHANNEL="msedge"
node worker.js login
```

The Studio backend invokes `worker.js generate` with JSON on stdin. The worker returns one JSON object on stdout, saves a temporary generated image under `storage/chatgpt-image-worker`, and the Python backend validates and moves it into the GPT Director task frame store.

No OpenAI API key is used. This relies on ChatGPT web UI automation and selectors may require maintenance when the website changes.
