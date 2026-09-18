# ComfyWorkflowStudio ChatGPT Image Worker

Local browser automation used by ComfyWorkflowStudio to generate one GPT Director shot keyframe at a time through a dedicated ChatGPT web browser session.

The implementation is inspired by the architecture of `leixyou/chatgpt-web-image-mcp` (MIT). See `THIRD_PARTY_NOTICES.md`.

## Setup

```powershell
cd D:\ComfyWorkflowStudio\tools\chatgpt-image
npm install
```

## Recommended Windows login: normal Chrome + local CDP

Google may reject OAuth sign-in inside a browser launched directly by Playwright with a "browser or app may not be secure" message. On Windows, the recommended login path is therefore to launch a normal dedicated Chrome instance yourself, then let the worker attach to it over localhost CDP.

1. From the project root, run:

```powershell
.\tools\chatgpt-image\start-cdp-chrome.cmd
```

2. In the Chrome window that opens, sign in to ChatGPT normally. This is a dedicated profile under:

```text
storage\chatgpt-image-browser\cdp-profile
```

3. Check readiness. ComfyWorkflowStudio now defaults to local CDP `http://127.0.0.1:9222`, so no environment variable is required:

```powershell
node tools/chatgpt-image/worker.js check
```

By default the CDP Chrome opens the project GPT `童语工坊 · AI动画编剧导演`. Override it only when needed with `CWS_CHATGPT_IMAGE_URL`.

Expected result includes:

```json
{
  "ok": true,
  "ready": true,
  "authenticated": true,
  "browserMode": "cdp"
}
```

In CDP mode the worker does not close the operator-owned Chrome window.

## Fallback: Playwright-launched dedicated profile

You can still use:

```powershell
node tools/chatgpt-image/worker.js login
```

This opens a Playwright-managed dedicated browser profile. It works for sites that accept that browser session, but some identity providers such as Google may reject OAuth sign-in in automated browsers. If that happens, use the CDP flow above instead of attempting to bypass the provider's security checks.

The browser profile stores the normal signed-in session locally. Passwords, MFA codes and cookies are never read or exported by ComfyWorkflowStudio.

If Chrome is unavailable but Microsoft Edge is installed:

```powershell
$env:CWS_CHATGPT_IMAGE_CHANNEL="msedge"
node tools/chatgpt-image/worker.js login
```

The Studio backend invokes `worker.js generate` with JSON on stdin. The worker returns one JSON object on stdout, saves a temporary generated image under `storage/chatgpt-image-worker`, and the Python backend validates and moves it into the GPT Director task frame store.

No OpenAI API key is used. This relies on ChatGPT web UI automation and selectors may require maintenance when the website changes.
