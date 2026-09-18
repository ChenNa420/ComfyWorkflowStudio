import assert from 'node:assert/strict'
import test from 'node:test'

import { findRelayedTool, firstText, parseArgs } from '../smoke-test.mjs'
import { parseArgs as parseVisionArgs, parseJsonObject } from '../gpt-visual-smoke.mjs'

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
