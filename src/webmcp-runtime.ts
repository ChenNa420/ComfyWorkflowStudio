type WebMcpRuntimeMode = 'native' | 'mcp-b-polyfill' | 'unavailable'

export type WebMcpRuntimeStatus = {
  mode: WebMcpRuntimeMode
  nativeDetected: boolean
  modelContextAvailable: boolean
  relayEmbedLoaded: boolean
  relayEndpoint: string
  runtimeSource: string
  error: string
}

declare global {
  interface Window {
    __cwsWebMcpRuntime?: WebMcpRuntimeStatus
  }
}

const MCP_B_GLOBAL_URL = 'https://cdn.jsdelivr.net/npm/@mcp-b/global@5.1.0/dist/index.iife.js'
const MCP_B_RELAY_EMBED_URL = 'https://cdn.jsdelivr.net/npm/@mcp-b/webmcp-local-relay@5.1.0/dist/browser/embed.js'
const RELAY_ENDPOINT = 'ws://127.0.0.1:9333'
const LOCAL_ORIGINS = new Set(['http://127.0.0.1:5174', 'http://localhost:5174'])

function modelContextAvailable() {
  return typeof (document as any).modelContext?.registerTool === 'function'
}

function loadScript(src: string, attributes: Record<string, string> = {}, timeoutMs = 10000): Promise<void> {
  const existing = document.querySelector<HTMLScriptElement>(`script[src="${src}"]`)
  if (existing?.dataset.cwsLoaded === '1') return Promise.resolve()

  return new Promise((resolve, reject) => {
    const script = existing || document.createElement('script')
    let settled = false
    const finish = (error?: Error) => {
      if (settled) return
      settled = true
      window.clearTimeout(timer)
      if (error) reject(error)
      else {
        script.dataset.cwsLoaded = '1'
        resolve()
      }
    }
    const timer = window.setTimeout(() => finish(new Error(`Timed out loading ${src}`)), timeoutMs)

    script.addEventListener('load', () => finish(), { once: true })
    script.addEventListener('error', () => finish(new Error(`Failed to load ${src}`)), { once: true })

    if (!existing) {
      script.src = src
      for (const [name, value] of Object.entries(attributes)) script.setAttribute(name, value)
      document.head.appendChild(script)
    }
  })
}

function publish(status: WebMcpRuntimeStatus) {
  window.__cwsWebMcpRuntime = status
  window.dispatchEvent(new CustomEvent('cws:webmcp-runtime-ready', { detail: status }))
  return status
}

export async function initializeWebMcpBrowserRuntime(): Promise<WebMcpRuntimeStatus> {
  const nativeDetected = modelContextAvailable()
  const isLocalStudio = LOCAL_ORIGINS.has(window.location.origin)
  let runtimeError = ''

  if (isLocalStudio) {
    try {
      await loadScript(MCP_B_GLOBAL_URL)
    } catch (error) {
      runtimeError = error instanceof Error ? error.message : 'MCP-B runtime failed to load'
    }
  }

  const available = modelContextAvailable()
  let relayEmbedLoaded = false

  if (available && isLocalStudio) {
    try {
      await loadScript(
        MCP_B_RELAY_EMBED_URL,
        {
          'data-relay-host': '127.0.0.1',
          'data-relay-port': '9333',
          'data-auto-connect': 'true',
          'data-request-timeout': '120000',
        },
      )
      relayEmbedLoaded = true
    } catch (error) {
      const message = error instanceof Error ? error.message : 'WebMCP relay embed failed to load'
      runtimeError = runtimeError ? `${runtimeError}; ${message}` : message
    }
  }

  return publish({
    mode: available ? (nativeDetected ? 'native' : 'mcp-b-polyfill') : 'unavailable',
    nativeDetected,
    modelContextAvailable: available,
    relayEmbedLoaded,
    relayEndpoint: RELAY_ENDPOINT,
    runtimeSource: available
      ? (nativeDetected ? 'Browser native WebMCP + MCP-B bridge' : 'MCP-B 5.1.0 polyfill + bridge')
      : 'No WebMCP runtime',
    error: runtimeError,
  })
}
