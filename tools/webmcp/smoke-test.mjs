import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { Client } from '@modelcontextprotocol/client'
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio'

const here = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(here, '../..')
const relayCli = path.join(here, 'node_modules', '@mcp-b', 'webmcp-local-relay', 'dist', 'cli.mjs')

export function parseArgs(argv) {
  const result = { taskId: '', page: null, timeoutMs: 20000 }
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '--task-id') result.taskId = String(argv[++i] || '')
    else if (arg === '--page') result.page = Number.parseInt(String(argv[++i] || ''), 10)
    else if (arg === '--timeout-ms') result.timeoutMs = Number.parseInt(String(argv[++i] || ''), 10)
    else if (arg === '--help' || arg === '-h') result.help = true
    else throw new Error('Unknown argument: ' + arg)
  }
  if (result.taskId && !/^gdt-[a-f0-9]{32}$/.test(result.taskId)) throw new Error('Invalid taskId')
  if (result.page !== null && (!Number.isInteger(result.page) || result.page < 1)) throw new Error('Invalid page')
  return result
}

export function firstText(result) {
  if (!result || !Array.isArray(result.content)) return ''
  const item = result.content.find((entry) => entry && entry.type === 'text' && typeof entry.text === 'string')
  return item ? item.text : ''
}

export function findRelayedTool(tools, baseName) {
  return tools.find((tool) => tool.name === baseName)
    || tools.find((tool) => tool.name.startsWith(baseName + '_'))
    || null
}

function parseJsonText(result, label) {
  const value = firstText(result)
  if (!value) throw new Error(label + ' returned no text')
  try { return JSON.parse(value) }
  catch { throw new Error(label + ' did not return JSON') }
}

async function withTimeout(promise, ms, label) {
  let timer
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(label + ' timed out')), ms)
      }),
    ])
  } finally {
    clearTimeout(timer)
  }
}

async function waitFor(label, timeoutMs, probe) {
  const started = Date.now()
  let lastError = null
  while (Date.now() - started < timeoutMs) {
    try {
      const value = await probe()
      if (value) return value
    } catch (error) {
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, 400))
  }
  if (lastError) throw lastError
  throw new Error(label + ' timed out')
}

async function main() {
  const options = parseArgs(process.argv.slice(2))
  if (options.help) {
    console.log('Usage: node tools/webmcp/smoke-test.mjs [--task-id gdt-...] [--page N]')
    return
  }
  if (!existsSync(relayCli)) throw new Error('Run: npm install --prefix tools\\webmcp')

  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [
      relayCli,
      '--host', '127.0.0.1',
      '--port', '9333',
      '--widget-origin', 'http://127.0.0.1:5174,http://localhost:5174',
      '--label', 'ComfyWorkflowStudio Smoke Client',
    ],
    cwd: repoRoot,
    stderr: 'pipe',
  })

  const relayLog = []
  transport.stderr?.on('data', (chunk) => relayLog.push(String(chunk)))

  const client = new Client(
    { name: 'comfy-workflow-studio-relay-smoke', version: '1.0.0' },
    { capabilities: {}, versionNegotiation: { mode: 'auto' } },
  )

  try {
    console.log('[1/5] MCP client connect')
    await withTimeout(client.connect(transport), options.timeoutMs, 'connect')
    console.log('      PASS')

    console.log('[2/5] webmcp_list_sources')
    const sourceDiscovery = await waitFor('ComfyWorkflowStudio browser source', options.timeoutMs, async () => {
      const sourcesResult = await client.callTool({ name: 'webmcp_list_sources', arguments: {} })
      const sources = parseJsonText(sourcesResult, 'webmcp_list_sources')
      const sourcesText = JSON.stringify(sources)
      if (sourcesText.includes('127.0.0.1:5174') || sourcesText.includes('localhost:5174')) {
        return { sources, sourcesText }
      }
      return null
    })
    console.log('      PASS - Studio browser source connected')

    console.log('[3/5] webmcp_list_tools + tools/list')
    const required = [
      'get_comic_story_task',
      'get_comic_story_page',
      'import_gpt_story',
      'complete_gpt_story_task',
      'probe_source_page_image',
      'probe_keyframe_transfer',
    ]
    const toolDiscovery = await waitFor('6/6 Studio relay tools', options.timeoutMs, async () => {
      const listResult = await client.callTool({ name: 'webmcp_list_tools', arguments: {} })
      const management = parseJsonText(listResult, 'webmcp_list_tools')
      const managementText = JSON.stringify(management)
      if (!required.every((name) => managementText.includes(name))) return null

      const listed = await client.listTools()
      if (!required.every((name) => findRelayedTool(listed.tools, name))) return null
      return { management, toolList: listed }
    })
    const toolList = toolDiscovery.toolList
    console.log('      PASS - 6/6 tools')

    if (!options.taskId) {
      console.log('[4/5] get_comic_story_task SKIP')
      console.log('[5/5] get_comic_story_page SKIP')
      console.log('\nWebMCP Relay Smoke Test = PASS (discovery)')
      return
    }

    console.log('[4/5] get_comic_story_task')
    const taskTool = findRelayedTool(toolList.tools, 'get_comic_story_task')
    const taskResult = await withTimeout(
      client.callTool({ name: taskTool.name, arguments: { taskId: options.taskId } }),
      options.timeoutMs,
      'get_comic_story_task',
    )
    if (taskResult.isError) throw new Error(firstText(taskResult) || 'task tool failed')
    if (!JSON.stringify(taskResult).includes(options.taskId)) throw new Error('taskId missing from result')
    console.log('      PASS')

    if (options.page === null) {
      console.log('[5/5] get_comic_story_page SKIP')
      console.log('\nWebMCP Relay Smoke Test = PASS (task invocation)')
      return
    }

    console.log('[5/5] get_comic_story_page')
    const pageTool = findRelayedTool(toolList.tools, 'get_comic_story_page')
    const pageResult = await withTimeout(
      client.callTool({ name: pageTool.name, arguments: { taskId: options.taskId, page: options.page } }),
      Math.max(options.timeoutMs, 60000),
      'get_comic_story_page',
    )
    if (pageResult.isError) throw new Error(firstText(pageResult) || 'page tool failed')
    const imageItem = Array.isArray(pageResult.content)
      ? pageResult.content.find((item) => item && item.type === 'image')
      : null
    if (!imageItem || typeof imageItem.data !== 'string' || !imageItem.data.length || !imageItem.mimeType) {
      throw new Error('ImageContent missing')
    }
    console.log('      PASS - ' + imageItem.mimeType + ', base64 chars=' + imageItem.data.length)
    console.log('\nWebMCP Relay Smoke Test = PASS (task + ImageContent)')
  } finally {
    await client.close().catch(() => undefined)
    if (relayLog.length) {
      const tail = relayLog.join('').trim().split(/\r?\n/).filter(Boolean).slice(-3)
      if (tail.length) console.log('\n[relay] ' + tail.join('\n[relay] '))
    }
  }
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href
if (isMain) {
  main().catch((error) => {
    console.error('\nWebMCP Relay Smoke Test = FAIL\n' + (error instanceof Error ? error.message : String(error)))
    process.exitCode = 1
  })
}
