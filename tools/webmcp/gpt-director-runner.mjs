import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { Client } from '@modelcontextprotocol/client'
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio'

import { BrowserSession } from '../chatgpt-image/browser-session.js'
import { SELECTORS } from '../chatgpt-image/chatgpt-page.js'
import { loadConfig } from '../chatgpt-image/config.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(here, '../..')
const relayCli = path.join(here, 'node_modules', '@mcp-b', 'webmcp-local-relay', 'dist', 'cli.mjs')
const REQUIRED_TOOLS = [
  'get_comic_story_task',
  'get_comic_story_page',
  'import_gpt_story',
  'complete_gpt_story_task',
]

export function parseArgs(argv) {
  const result = { taskId: '', timeoutMs: 420000 }
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--task-id') result.taskId = String(argv[++index] || '')
    else if (arg === '--timeout-ms') result.timeoutMs = Number.parseInt(String(argv[++index] || ''), 10)
    else if (arg === '--help' || arg === '-h') result.help = true
    else throw new Error('Unknown argument: ' + arg)
  }
  if (!result.help && !/^gdt-[a-f0-9]{32}$/.test(result.taskId)) throw new Error('Invalid taskId')
  if (!Number.isInteger(result.timeoutMs) || result.timeoutMs < 60000 || result.timeoutMs > 900000) {
    throw new Error('--timeout-ms must be between 60000 and 900000')
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
  const unfenced = raw.replace(/^\x60\x60\x60(?:json)?\s*/i, '').replace(/\s*\x60\x60\x60$/i, '').trim()
  const start = unfenced.indexOf('{')
  const end = unfenced.lastIndexOf('}')
  if (start < 0 || end <= start) throw new Error('GPT response does not contain a JSON object')
  const candidate = unfenced.slice(start, end + 1)
  try {
    return JSON.parse(candidate)
  } catch (error) {
    throw new Error('GPT returned invalid JSON: ' + (error instanceof Error ? error.message : String(error)))
  }
}

function resultObject(result, label) {
  if (result && result.structuredContent && typeof result.structuredContent === 'object') return result.structuredContent
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
      '--label', 'ComfyWorkflowStudio GPT Director Auto',
    ],
    cwd: repoRoot,
    stderr: 'pipe',
  })
  const relayLog = []
  if (transport.stderr) transport.stderr.on('data', (chunk) => relayLog.push(String(chunk)))
  const client = new Client(
    { name: 'comfy-workflow-studio-gpt-director-auto', version: '1.0.0' },
    { capabilities: {}, versionNegotiation: { mode: 'auto' } },
  )
  await client.connect(transport)
  return { client, relayLog }
}

async function waitForTools(client, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const listed = await client.listTools()
    const found = {}
    let complete = true
    for (const name of REQUIRED_TOOLS) {
      const tool = findRelayedTool(listed.tools, name)
      if (!tool) complete = false
      else found[name] = tool
    }
    if (complete) return found
    await new Promise((resolve) => setTimeout(resolve, 400))
  }
  throw new Error('Studio WebMCP production tools were not discovered')
}

async function readTask(client, tool, taskId) {
  const result = await client.callTool({ name: tool.name, arguments: { taskId } })
  if (result.isError) throw new Error(firstText(result) || 'get_comic_story_task failed')
  const task = resultObject(result, 'get_comic_story_task')
  if (!task || task.id !== taskId) throw new Error('Task ID mismatch')
  return task
}

async function fetchSelectedPages(client, tool, task, inputDir) {
  await fs.rm(inputDir, { recursive: true, force: true })
  await fs.mkdir(inputDir, { recursive: true })
  const files = []
  for (const pageNumber of task.source.selectedPages || []) {
    const result = await client.callTool({
      name: tool.name,
      arguments: { taskId: task.id, page: pageNumber },
    })
    if (result.isError) throw new Error(firstText(result) || ('get_comic_story_page failed for page ' + pageNumber))
    const image = Array.isArray(result.content)
      ? result.content.find((item) => item && item.type === 'image')
      : null
    if (!image || typeof image.data !== 'string' || !image.data || !image.mimeType) {
      throw new Error('Page ' + pageNumber + ' did not return ImageContent')
    }
    const filePath = path.join(
      inputDir,
      'page-' + String(pageNumber).padStart(3, '0') + '.' + extensionForMime(image.mimeType),
    )
    await fs.writeFile(filePath, Buffer.from(image.data, 'base64'))
    files.push({ page: pageNumber, filePath, mime: image.mimeType })
  }
  if (!files.length) throw new Error('Task has no selected source pages')
  return files
}

export function composeDirectorPrompt(task) {
  const settings = task.settings || {}
  const pages = Array.isArray(task.source && task.source.selectedPages) ? task.source.selectedPages : []
  return [
    '你正在为 ComfyWorkflowStudio 执行儿童英语动画 GPT Director 正式任务。',
    '本消息附带的图片就是该任务全部真实漫画源页面。必须直接观察这些图片，再进行多页综合理解和重新创作。',
    '不要根据文件名、页码、metadata 或历史记忆猜测画面；不要机械翻译或逐格复刻。',
    '',
    'Task ID: ' + String(task.id || ''),
    'Selected pages: ' + pages.join(', '),
    'Target age: ' + String(settings.targetAge || ''),
    'English level: ' + String(settings.level || ''),
    'Style: ' + String(settings.style || ''),
    'Language: ' + String(settings.language || ''),
    'Target duration: ' + String(settings.duration || ''),
    'Aspect ratio: ' + String(settings.aspectRatio || ''),
    'Adaptation strength: ' + String(settings.adaptationStrength || ''),
    'Preserve visual mood: ' + String(Boolean(settings.preserveVisualMood)),
    'Preserve composition reference: ' + String(Boolean(settings.preserveComposition)),
    'Replace characters: ' + String(Boolean(settings.replaceCharacters)),
    'Allow ending change: ' + String(Boolean(settings.allowEndingChange)),
    'Extra request: ' + String(settings.extraRequest || ''),
    '',
    '请先综合理解所有页面中的角色、动作、场景、事件顺序、视觉氛围和构图关系，再创作一个适合儿童英语动画的新故事。',
    '自动决定合理镜头数量，不固定 6 镜头。',
    '',
    '只返回一个完整合法 JSON 对象。不要 Markdown 代码围栏，不要解释，不要在 JSON 前后添加文字。',
    '顶层字段必须严格包含：sourceUnderstanding、creativeStory、characterDefinitions、sceneDefinitions、shots。',
    'creativeStory 必须包含：title、summary、story、adaptationNotes。',
    'shots 必须为 1–24 个。',
    '每个 shot 必须包含：shotId、title、duration、storyPurpose、speaker、english、chinese、keyframeDescription、imagePrompt、videoPrompt、negativePrompt、sourcePages。',
    'duration 必须 > 0 且 <= 10。',
    'shotId 必须唯一。',
    'imagePrompt 和 videoPrompt 必须非空。',
    'sourcePages 必须至少包含 1 页，并且只能引用这些页：' + pages.join(', ') + '。',
    'speaker 没有对白时使用 null。',
    '英文对白要简短自然并适合目标英语等级；chinese 要准确对应英文。',
    'sourceUnderstanding 请明确写出你从真实图片中观察到的多页故事关系与视觉依据。',
  ].join('\n')
}

async function uploadFiles(page, filePaths) {
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
  await input.setInputFiles(filePaths)
  await page.waitForTimeout(Math.min(10000, 1800 + filePaths.length * 500))
}

async function isGenerating(page) {
  const locators = page.locator(SELECTORS.generating)
  const count = await locators.count().catch(() => 0)
  for (let index = 0; index < count; index += 1) {
    if (await locators.nth(index).isVisible().catch(() => false)) return true
  }
  return false
}

async function sendPrompt(page, prompt, timeoutMs) {
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
      if (text && !generating && stableSince && Date.now() - stableSince >= 3000) return text
    }
    await page.waitForTimeout(1000)
  }
  throw new Error('Timed out waiting for GPT Director response')
}

async function runChatGPT(task, files, timeoutMs) {
  const config = loadConfig()
  const session = new BrowserSession(config)
  try {
    const page = await session.getPage(config.chatgptUrl)
    // Do not gate the production flow on a separate login precheck.
    // The real composer/file-upload path below is the authoritative runtime check.
    await uploadFiles(page, files.map((item) => item.filePath))
    const responseText = await sendPrompt(page, composeDirectorPrompt(task), timeoutMs)
    return { result: parseJsonObject(responseText), gptUrl: page.url() }
  } finally {
    await session.close()
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2))
  if (options.help) {
    console.log('Usage: node tools/webmcp/gpt-director-runner.mjs --task-id gdt-...')
    return
  }

  await fs.access(relayCli)
  const inputDir = path.join(repoRoot, 'storage', 'gpt-director', options.taskId, '.director-input')
  let client = null
  let relayLog = []

  try {
    console.error('[1/6] Connecting to WebMCP Relay and Studio tools...')
    const relay = await connectRelay()
    client = relay.client
    relayLog = relay.relayLog
    const tools = await waitForTools(client, 20000)
    console.error('      PASS')

    console.error('[2/6] Reading task and all selected page ImageContent...')
    const task = await readTask(client, tools.get_comic_story_task, options.taskId)
    const files = await fetchSelectedPages(client, tools.get_comic_story_page, task, inputDir)
    console.error('      PASS - ' + files.length + ' page(s)')

    console.error('[3/6] Opening 童语工坊 GPT and uploading all source pages...')
    const generated = await runChatGPT(task, files, options.timeoutMs)
    console.error('      PASS - GPT returned structured JSON')

    console.error('[4/6] Importing story through WebMCP...')
    const imported = await client.callTool({
      name: tools.import_gpt_story.name,
      arguments: { taskId: options.taskId, result: generated.result },
    })
    if (imported.isError) throw new Error(firstText(imported) || 'import_gpt_story failed')
    console.error('      PASS')

    console.error('[5/6] Completing GPT Director task through WebMCP...')
    const completed = await client.callTool({
      name: tools.complete_gpt_story_task.name,
      arguments: { taskId: options.taskId },
    })
    if (completed.isError) throw new Error(firstText(completed) || 'complete_gpt_story_task failed')
    console.error('      PASS')

    console.error('[6/6] Done')
    process.stdout.write(JSON.stringify({
      ok: true,
      taskId: options.taskId,
      title: String(generated.result && generated.result.creativeStory && generated.result.creativeStory.title || ''),
      shotCount: Array.isArray(generated.result && generated.result.shots) ? generated.result.shots.length : 0,
      sourcePages: files.map((item) => item.page),
      gptUrl: generated.gptUrl,
    }) + '\n')
  } catch (error) {
    process.stdout.write(JSON.stringify({
      ok: false,
      code: 'GPT_DIRECTOR_RUN_FAILED',
      message: error instanceof Error ? error.message : String(error),
    }) + '\n')
    process.exitCode = 1
  } finally {
    if (client) await client.close().catch(() => undefined)
    await fs.rm(inputDir, { recursive: true, force: true }).catch(() => undefined)
    if (relayLog.length) {
      const tail = relayLog.join('').trim().split(/\r?\n/).filter(Boolean).slice(-3)
      if (tail.length) console.error('[relay] ' + tail.join('\n[relay] '))
    }
  }
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href
if (isMain) void main()
