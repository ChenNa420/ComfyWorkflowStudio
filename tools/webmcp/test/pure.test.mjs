import assert from 'node:assert/strict'
import test from 'node:test'

import { findRelayedTool, firstText, parseArgs } from '../smoke-test.mjs'

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
