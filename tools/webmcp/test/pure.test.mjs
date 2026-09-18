import assert from 'node:assert/strict'
import test from 'node:test'

import { findRelayedTool, firstText, parseArgs } from '../smoke-test.mjs'
import { parseArgs as parseVisionArgs, parseJsonObject } from '../gpt-visual-smoke.mjs'
import { parseArgs as parseDirectorArgs, parseJsonObject as parseDirectorJson, composeDirectorPrompt, completeJsonResponse, parseableJsonResponse, validateProductionResult, isNewAssistantResponse, jsonRepairPrompt } from '../gpt-director-runner.mjs'

test('parseArgs accepts task and page', () => {
  const value = parseArgs(['--task-id', 'gdt-0123456789abcdef0123456789abcdef', '--page', '4'])
  assert.equal(value.taskId, 'gdt-0123456789abcdef0123456789abcdef')
  assert.equal(value.page, 4)
})

test('parseArgs rejects unsafe task ids', () => {
  assert.throws(() => parseArgs(['--task-id', '../etc/passwd']))
})

test('findRelayedTool supports unique and suffixed relay names', () => {
  assert.equal(findRelayedTool([{ name: 'get_comic_story_task' }], 'get_comic_story_task')?.name, 'get_comic_story_task')
  assert.equal(findRelayedTool([{ name: 'get_comic_story_task_ab12' }], 'get_comic_story_task')?.name, 'get_comic_story_task_ab12')
})

test('firstText returns MCP text content', () => {
  assert.equal(firstText({ content: [{ type: 'text', text: 'hello' }] }), 'hello')
})


test('vision parseArgs requires task and page', () => {
  const value = parseVisionArgs(['--task-id', 'gdt-0123456789abcdef0123456789abcdef', '--page', '7'])
  assert.equal(value.taskId, 'gdt-0123456789abcdef0123456789abcdef')
  assert.equal(value.page, 7)
})

test('vision parseArgs rejects missing page', () => {
  assert.throws(() => parseVisionArgs(['--task-id', 'gdt-0123456789abcdef0123456789abcdef']))
})

test('parseJsonObject accepts fenced JSON', () => {
  const value = parseJsonObject("```json\\n{\"page\":7,\"visibleSummary\":\"ok\"}\\n```")
  assert.equal(value.page, 7)
  assert.equal(value.visibleSummary, 'ok')
})

test('parseJsonObject rejects text without JSON', () => {
  assert.throws(() => parseJsonObject('hello'))
})


test('director parseArgs requires safe task id', () => {
  const value = parseDirectorArgs(['--task-id', 'gdt-0123456789abcdef0123456789abcdef'])
  assert.equal(value.taskId, 'gdt-0123456789abcdef0123456789abcdef')
  assert.throws(() => parseDirectorArgs(['--task-id', '../bad']))
})

test('director parseJsonObject accepts fenced output', () => {
  const value = parseDirectorJson("```json\n{\"creativeStory\":{\"title\":\"Demo\"},\"shots\":[]}\n```")
  assert.equal(value.creativeStory.title, 'Demo')
  assert.throws(() => parseDirectorJson('not-json'))
})

test('director prompt includes selected pages and strict result fields', () => {
  const prompt = composeDirectorPrompt({
    id: 'gdt-0123456789abcdef0123456789abcdef',
    source: { selectedPages: [4, 6, 9] },
    settings: { targetAge: '3-6岁', level: 'Pre-A1', style: '温馨冒险' },
  })
  assert.match(prompt, /4, 6, 9/)
  assert.match(prompt, /sourceUnderstanding/)
  assert.match(prompt, /imagePrompt/)
  assert.match(prompt, /videoPrompt/)
})


test('completeJsonResponse detects finished production payload', () => {
  const text = JSON.stringify({
    sourceUnderstanding: { summary: 'ok' },
    creativeStory: { title: 'Demo' },
    characterDefinitions: [],
    sceneDefinitions: [],
    shots: [{ shotId: 'S01' }],
  })
  assert.equal(completeJsonResponse(text), true)
  assert.equal(completeJsonResponse('{"creativeStory":{"title":"Demo"},"shots":['), false)
  assert.equal(completeJsonResponse('{"creativeStory":{"title":"Demo"},"shots":[]}'), false)
})


test('recycled assistant node counts as a new response when text changes', () => {
  const baseline = { count: 1, lastText: 'old answer' }
  assert.equal(isNewAssistantResponse(1, 'new answer', baseline), true)
  assert.equal(isNewAssistantResponse(1, 'old answer', baseline), false)
  assert.equal(isNewAssistantResponse(2, 'another answer', baseline), true)
})

test('parseableJsonResponse accepts any complete JSON object without implying production validity', () => {
  assert.equal(parseableJsonResponse('{"error":"repair unavailable"}'), true)
  assert.equal(parseableJsonResponse('{"creativeStory":'), false)
})

test('production validator rejects error objects and incomplete payloads', () => {
  assert.throws(() => validateProductionResult({ error: 'repair unavailable' }), /error object/)
  assert.throws(() => validateProductionResult({
    sourceUnderstanding: {},
    creativeStory: { title: 'Demo' },
    characterDefinitions: [],
    sceneDefinitions: [],
    shots: [],
  }), /1-24/)
})

test('production validator accepts required production structure', () => {
  const value = {
    sourceUnderstanding: { summary: 'ok' },
    creativeStory: { title: 'Demo' },
    characterDefinitions: [],
    sceneDefinitions: [],
    shots: [{
      shotId: 'S01',
      imagePrompt: 'frame',
      videoPrompt: 'motion',
      sourcePages: [4],
    }],
  }
  assert.equal(validateProductionResult(value), value)
})

test('json repair prompt preserves content, demands escaped quotes, and carries original reply', () => {
  const original = '{"english":"Bobo, "wait!""}'
  const prompt = jsonRepairPrompt('Unexpected token', original)
  assert.match(prompt, /保持故事、角色、场景、镜头数量、对白/)
  assert.match(prompt, /只修复 JSON 语法/)
  assert.match(prompt, /\\\"/)
  assert.match(prompt, /Unexpected token/)
  assert.match(prompt, /待修复的上一版完整原文开始/)
  assert.match(prompt, /Bobo/)
  assert.match(prompt, /待修复的上一版完整原文结束/)
})
