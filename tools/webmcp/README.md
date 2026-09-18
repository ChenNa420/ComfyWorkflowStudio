# WebMCP Browser Bridge

ComfyWorkflowStudio keeps its existing page tools on `document.modelContext` and adds a browser fallback for Chrome/Edge that do not expose native WebMCP.

## Browser runtime

The Studio boot sequence loads pinned MCP-B browser assets only on the local Studio origins:

- `http://127.0.0.1:5174`
- `http://localhost:5174`

Pinned runtime:

- `@mcp-b/global@5.1.0`
- `@mcp-b/webmcp-local-relay@5.1.0` browser embed

When native WebMCP exists, MCP-B wraps it. When it does not, MCP-B supplies `document.modelContext`.

The relay embed only targets:

- host: `127.0.0.1`
- port: `9333`

No LAN address and no wildcard origin are configured by ComfyWorkflowStudio.

## Local relay

The relay package requires Node.js 22+.

For a quick local relay process:

```bat
tools\webmcp\start-local-relay.cmd
```

The relay accepts browser tools only from:

```text
http://127.0.0.1:5174
http://localhost:5174
```

For normal MCP-client usage, prefer letting the MCP client launch the relay over stdio. A sample configuration is in:

```text
tools/webmcp/mcp-client-config.example.json
```

## Verification in Chrome/Edge

Open:

```text
http://127.0.0.1:5174
```

Then DevTools Console:

```js
typeof document.modelContext?.registerTool
```

Expected:

```text
"function"
```

On the Comic Story page the header should show:

```text
WebMCP 已就绪
6/6 工具
MCP-B Polyfill
Relay Embed 已加载
```

The six Studio tools are:

- `get_comic_story_task`
- `get_comic_story_page`
- `import_gpt_story`
- `complete_gpt_story_task`
- `probe_source_page_image`
- `probe_keyframe_transfer`

The first four are the production story bridge. The two probe tools remain developer diagnostics.

## Security

The bridge is intended for local development. Do not change the relay host to `0.0.0.0` and do not use `--widget-origin *`.

The relay does not make a normal ChatGPT web tab automatically discover another tab's tools. An MCP-compatible client still needs to connect to the local relay.


## One-command smoke test

Keep these running first:

1. `start-workbench.cmd` (it now keeps a persistent WebMCP Relay owner on `127.0.0.1:9333` when Node.js 22+ is available)
2. ComfyWorkflowStudio Web at `http://127.0.0.1:5174`
3. The Comic Story tab showing `WebMCP 已就绪 · 6/6` and `Relay Embed 已加载`

If the Studio page was open before the relay started, refresh that page once. The smoke-test client deliberately requires an existing relay owner so its stdio relay joins in client mode instead of creating a short-lived server.

Then run:

```bat
tools\webmcp\test-relay.cmd
```

The first run installs the small test-client dependencies under `tools/webmcp/node_modules`. It validates:

- MCP stdio client can attach to the existing 9333 relay in client mode
- `webmcp_list_sources` sees the ComfyWorkflowStudio browser tab
- `webmcp_list_tools` reports all six Studio tools
- MCP `tools/list` exposes those six dynamic browser tools

To also invoke a real GPT Director task:

```bat
tools\webmcp\test-relay.cmd gdt-0123456789abcdef0123456789abcdef
```

To verify a selected source page returns real MCP `ImageContent`:

```bat
tools\webmcp\test-relay.cmd gdt-0123456789abcdef0123456789abcdef 4
```

The page number must be in that task's `selectedPages`; otherwise the Studio API will correctly reject it.
