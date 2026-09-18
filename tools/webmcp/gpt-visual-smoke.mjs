import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { Client } from '@modelcontextprotocol/client'
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio'

import { BrowserSession } from '../chatgpt-image/browser-session.js'
import { ChatGPTPage, SELECTORS } from '../chatgpt-image/chatgpt-page.js'
import { loadConfig } from '../chatgpt-image/config.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(here, '../..')
const relayCli = path.join(here, 'node_modules', '@mcp-b', 'webmcp-local-relay', 'dist', 'cli.mjs')

export function parseArgs(argv) {
  const result = { taskId: '', page: null, timeoutMs: 180000 }
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--task-id') result.taskId = String(argv[++index] || '')
    else if (arg === '--page') result.page = Number.parseInt(String(argv[++index] || ''), 10)
    else if (arg === '--timeout-ms') result.timeoutMs = Number.parseInt(String(argv[++index] || ''), 10)
    else if (arg === '--help' || arg === '-h') result.help = true
    else throw new Error('Unknown argument: ' + arg)
  }
  if (!result.help && !/^gdt-[a-f0-9]{32}$/.test(result.taskId)) throw new Error('Invalid taskId')
  if (!result.help && (!Number.isInteger(result.page) || result.page < 1)) throw new Error('Invalid page')
  if (!Number.isInteger(result.timeoutMs) || result.timeoutMs < 30000 || result.timeoutMs > 600000) {
    throw new Error('--timeout-ms must be between 30000 and 600000')
  }
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

export function parseJsonObject(text) {
  const raw = String(text || '').trim()
  const unfenced = raw.replace(/^\`\`\`(?:json)?\s*/i, '').replace(/\s*\`\`\`$/i, '').trim()
  const start = unfenced.indexOf('{')
  const end = unfenced.lastIndexOf('}')
  if (start < 0 || end <= start) throw new Error('GPT response does not contain a JSON object')
  return JSON.parse(unfenced.slice(start, end + 1))
}

function resultObject(result, label) {
  if (result && result.structuredContent && typeof result.structuredContent === 'object') {
    return result.structuredContent
  }
  const text = firstText(result)
  if (!text) throw new Error(label + ' returned no JSON content')
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(label + ' returned invalid JSON')
  }
}

function extensionForMime(mime) {
  if (mime === 'image/png') return 'png'
  if (mime === 'image/webp') return 'webp'
  return 'jpg'
}

async function connectRelay() {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [
      relayCli,
      '--host', '127.0.0.1',
      '--port', '9333',
      '--widget-origin', 'http://127.0.0.1:5174,http://localhost:5174',
      '--label', 'ComfyWorkflowStudio GPT Vision Probe',
    ],
    cwd: repoRoot,
    stderr: 'pipe',
  })
  const relayLog = []
  if (transport.stderr) transport.stderr.on('data', (chunk) => relayLog.push(String(chunk)))
  const client = new Client(
    { name: 'comfy-workflow-studio-gpt-vision-probe', version: '1.0.0' },
    { capabilities: {}, versionNegotiation: { mode: 'auto' } },
  )
  await client.connect(transport)
  return { client, relayLog }
}

async function waitForTools(client, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const listed = await client.listTools()
    const taskTool = findRelayedTool(listed.tools, 'get_comic_story_task')
    const pageTool = findRelayedTool(listed.tools, 'get_comic_story_page')
    if (taskTool && pageTool) return { taskTool, pageTool }
    await new Promise((resolve) => setTimeout(resolve, 400))
  }
  throw new Error('Studio WebMCP tools were not discovered')
}

async function fetchImageContent(client, tools, taskId, pageNumber) {
  const taskResult = await client.callTool({
    name: tools.taskTool.name,
    arguments: { taskId },
  })
  if (taskResult.isError) throw new Error(firstText(taskResult) || 'get_comic_story_task failed')
  const task = resultObject(taskResult, 'get_comic_story_task')
  if (task.id !== taskId) throw new Error('Task ID mismatch')
  if (!Array.isArray(task.source?.selectedPages) || !task.source.selectedPages.includes(pageNumber)) {
    throw new Error('Requested page is not selected in this GPT Director task')
  }

  const pageResult = await client.callTool({
    name: tools.pageTool.name,
    arguments: { taskId, page: pageNumber },
  })
  if (pageResult.isError) throw new Error(firstText(pageResult) || 'get_comic_story_page failed')
  const image = Array.isArray(pageResult.content)
    ? pageResult.content.find((item) => item && item.type === 'image')
    : null
  if (!image || typeof image.data !== 'string' || !image.data || !image.mimeType) {
    throw new Error('get_comic_story_page did not return ImageContent')
  }
  return { task, image }
}

async function uploadImage(page, filePath) {
  let input = page.locator("input[type='file']").first()
  if (!(await input.count())) {
    const addButton = page.locator([
      "[data-testid='composer-plus-btn']",
      "button[aria-label*='Attach']",
      "button[aria-label*='上传']",
      "button[aria-label*='添加']",
    ].join(', ')).first()
    if (await addButton.count()) {
      await addButton.click().catch(() => undefined)
      await page.waitForTimeout(500)
    }
    input = page.locator("input[type='file']").first()
  }
  if (!(await input.count())) throw new Error('ChatGPT file upload input was not found')
  await input.setInputFiles(filePath)
  await page.waitForTimeout(1800)
}

async function isGenerating(page) {
  const locators = page.locator(SELECTORS.generating)
  const count = await locators.count().catch(() => 0)
  for (let index = 0; index < count; index += 1) {
    if (await locators.nth(index).isVisible().catch(() => false)) return true
  }
  return false
}

async function sendVisionPrompt(page, prompt, timeoutMs) {
  const beforeCount = await page.locator("[data-message-author-role='assistant']").count().catch(() => 0)
  const box = page.locator(SELECTORS.prompt).first()
  await box.waitFor({ state: 'visible', timeout: 20000 })
  try {
    await box.fill(prompt)
  } catch {
    await box.click()
    await page.keyboard.insertText(prompt)
  }

  const send = page.locator(SELECTORS.send).last()
  if ((await send.count()) > 0 && (await send.isVisible().catch(() => false))) await send.click()
  else await page.keyboard.press('Enter')

  const deadline = Date.now() + timeoutMs
  let stableText = ''
  let stableSince = 0
  while (Date.now() < deadline) {
    const turns = page.locator("[data-message-author-role='assistant']")
    const count = await turns.count().catch(() => 0)
    if (count > beforeCount) {
      const text = (await turns.last().innerText().catch(() => '')).trim()
      const generating = await isGenerating(page)
      if (text && text === stableText) {
        if (!stableSince) stableSince = Date.now()
      } else {
        stableText = text
        stableSince = text ? Date.now() : 0
      }
      if (text && !generating && stableSince && Date.now() - stableSince >= 2500) return text
    }
    await page.waitForTimeout(1000)
  }
  throw new Error('Timed out waiting for GPT visual response')
}

function visualPrompt(taskId, pageNumber) {
  return [
    '这是 ComfyWorkflowStudio 的真实漫画页视觉能力验收。',
    '请只观察我刚刚上传的这一张漫画页图片，不要根据文件名、任务名、历史记忆或常识补充画面中不存在的内容。',
    '',
    'Task ID: ' + taskId,
    'Source page: ' + pageNumber,
    '',
    '只返回一个合法 JSON 对象，不要 Markdown，不要解释。',
    '字段必须为：',
    '{',
    '  "page": number,',
    '  "visibleSummary": string,',
    '  "characters": [string],',
    '  "actions": [string],',
    '  "setting": string,',
    '  "visibleText": [string],',
    '  "distinctiveVisualDetails": [string],',
    '  "confidence": "high" | "medium" | "low"',
    '}',
    '',
    '如果文字看不清，请在 visibleText 中省略，不要猜。',
  ].join('\n')
}

async function runVisionProbe(taskId, pageNumber, image, timeoutMs, tempFile) {
  await fs.writeFile(tempFile, Buffer.from(image.data, 'base64'))
  const config = loadConfig()
  const session = new BrowserSession(config)
  try {
    const chatPage = await session.getPage(config.chatgptUrl)
    await new ChatGPTPage(chatPage, config).assertReady(20000)
    await uploadImage(chatPage, tempFile)
    const responseText = await sendVisionPrompt(chatPage, visualPrompt(taskId, pageNumber), timeoutMs)
    return {
      gptUrl: chatPage.url(),
      responseText,
      response: parseJsonObject(responseText),
    }
  } finally {
    await session.close()
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2))
  if (options.help) {
    console.log('Usage: node tools/webmcp/gpt-visual-smoke.mjs --task-id gdt-... --page N')
    return
  }

  await fs.access(relayCli)
  const tempDir = path.join(repoRoot, 'storage', 'gpt-director', options.taskId, '.vision-probe')
  await fs.mkdir(tempDir, { recursive: true })
  let client = null
  let relayLog = []

  try {
    console.log('[1/5] Connecting to existing WebMCP Relay...')
    const relay = await connectRelay()
    client = relay.client
    relayLog = relay.relayLog
    console.log('      PASS')

    console.log('[2/5] Discovering Studio source-page tools...')
    const tools = await waitForTools(client, 20000)
    console.log('      PASS')

    console.log('[3/5] Fetching real source page ImageContent through WebMCP...')
    const fetched = await fetchImageContent(client, tools, options.taskId, options.page)
    const extension = extensionForMime(fetched.image.mimeType)
    const tempFile = path.join(tempDir, 'page-' + String(options.page).padStart(3, '0') + '.' + extension)
    console.log('      PASS - ' + fetched.image.mimeType + ', base64 chars=' + fetched.image.data.length)

    console.log('[4/5] Uploading that image to 童语工坊 GPT through CDP Chrome...')
    const vision = await runVisionProbe(options.taskId, options.page, fetched.image, options.timeoutMs, tempFile)
    console.log('      PASS')

    const evidence = {
      taskId: options.taskId,
      page: options.page,
      mime: fetched.image.mimeType,
      gptUrl: vision.gptUrl,
      checkedAt: new Date().toISOString(),
      visualResponse: vision.response,
    }
    const evidencePath = path.join(repoRoot, 'storage', 'gpt-director', options.taskId, 'visual-probe.json')
    await fs.writeFile(evidencePath, JSON.stringify(evidence, null, 2), 'utf8')

    console.log('[5/5] GPT visual response')
    console.log(JSON.stringify(vision.response, null, 2))
    console.log('')
    console.log('GPT Visual ImageContent Probe = PASS')
    console.log('Evidence: storage/gpt-director/' + options.taskId + '/visual-probe.json')
  } catch (error) {
    console.error('')
    console.error('GPT Visual ImageContent Probe = FAIL')
    console.error(error instanceof Error ? error.message : String(error))
    process.exitCode = 1
  } finally {
    if (client) await client.close().catch(() => undefined)
    await fs.rm(tempDir, { recursive: true, force: true }).catch(() => undefined)
    if (relayLog.length) {
      const tail = relayLog.join('').trim().split(/\r?\n/).filter(Boolean).slice(-3)
      if (tail.length) console.error('[relay] ' + tail.join('\n[relay] '))
    }
  }
}

void main()
