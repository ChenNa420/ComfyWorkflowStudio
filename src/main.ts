import { createApp } from 'vue'
import StudioRoot from './StudioRoot.vue'
import { initializeWebMcpBrowserRuntime } from './webmcp-runtime'
import './style.css'
import './phase1d.css'
import './studio-root.css'

async function bootstrap() {
  try {
    await initializeWebMcpBrowserRuntime()
  } catch (error) {
    console.warn('[ComfyWorkflowStudio] WebMCP runtime initialization failed:', error)
  }
  createApp(StudioRoot).mount('#app')
}

void bootstrap()
