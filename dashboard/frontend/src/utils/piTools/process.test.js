import { describe, it, expect } from 'vitest'
import { parseProcess, processOutput, processStatusTone, processSummary } from './process'
import { parseToolCall } from './payload'

const startArgs =
  '{"action":"start","command":"cd /f/wt/backend && dotnet test HeapzillaMail.sln 2>&1 | tail -40","name":"hzm30-tests"}'

function tool(args, output = null, status = 'done') {
  const item = { id: 't1', name: 'process', args, output, status, durationMs: 3, truncated: false }
  return { ...parseToolCall(args, output, parseProcess), item }
}

describe('parseProcess', () => {
  it('reads a start process block', () => {
    const output = JSON.stringify({
      content: [{ type: 'text', text: 'Started process hzm30-tests (proc_4d64) with pid 330487.' }],
      details: {
        action: 'start',
        process: { id: 'proc_4d64', name: 'hzm30-tests', pid: 330487, command: 'cd /f && x', cwd: '/f/wt', status: 'running' },
      },
    })
    expect(tool(startArgs, output).view).toEqual({
      action: 'start',
      id: 'proc_4d64',
      name: 'hzm30-tests',
      pid: 330487,
      status: 'running',
      exitCode: null,
      command: 'cd /f && x',
      cwd: '/f/wt',
    })
  })

  it('reads output details', () => {
    const output =
      '{"content":[{"type":"text","text":"No output yet."}],"details":{"action":"output","id":"proc_4d64","processName":"hzm30-tests","processStatus":"running"}}'
    expect(tool('{"action":"output","id":"proc_4d64"}', output).view).toMatchObject({
      action: 'output',
      id: 'proc_4d64',
      name: 'hzm30-tests',
      status: 'running',
    })
  })

  it('reads a stop from args alone and from the result info', () => {
    expect(tool('{"action":"stop","id":"proc_4d64"}').view).toMatchObject({ action: 'stop', id: 'proc_4d64', name: null })
    const output = JSON.stringify({
      content: [{ type: 'text', text: 'Stopped.' }],
      details: { action: 'stop', result: { ok: true, info: { id: 'proc_e997', name: 'web', pid: 1033315, status: 'killed' } } },
    })
    expect(tool('{"action":"stop","id":"proc_e997"}', output).view).toMatchObject({ name: 'web', pid: 1033315, status: 'killed' })
  })

  it('tolerates unknown details and nothing at all', () => {
    expect(tool('{"action":"output","id":"proc_x"}', '{"content":[],"details":{"weird":true}}').view).toMatchObject({
      action: 'output',
      id: 'proc_x',
    })
    expect(parseProcess(null, null)).toBeNull()
  })
})

describe('processStatusTone', () => {
  it('maps statuses and a non-zero exit', () => {
    expect(processStatusTone('running', null)).toBe('warning')
    expect(processStatusTone('exited', 0)).toBe('success')
    expect(processStatusTone('success', null)).toBe('success')
    expect(processStatusTone('failed', null)).toBe('danger')
    expect(processStatusTone('killed', null)).toBe('danger')
    expect(processStatusTone('exited', 2)).toBe('danger')
    expect(processStatusTone('weird', null)).toBe('neutral')
  })
})

describe('processSummary', () => {
  it('summarizes each action', () => {
    const started =
      '{"content":[{"type":"text","text":"Started."}],"details":{"action":"start","process":{"name":"hzm30-tests","status":"running"}}}'
    expect(processSummary(tool(startArgs, started))).toBe(
      'start hzm30-tests · dotnet test HeapzillaMail.sln 2>&1 | tail -40 · running',
    )
    expect(processSummary(tool('{"action":"stop","id":"proc_4d64"}'))).toBe('stop proc_4d64')
    expect(processSummary(tool('{"action":"list"}'))).toBe('list')
  })

  it('reports a non-zero exit', () => {
    const output =
      '{"content":[{"type":"text","text":"Started."}],"details":{"action":"start","process":{"name":"demo","status":"exited","exitCode":1}}}'
    expect(processSummary(tool('{"action":"start","command":"echo hi","name":"demo"}', output))).toBe(
      'start demo · echo hi · exited · exit 1',
    )
  })

  it('falls back for an unknown action', () => {
    expect(processSummary(tool('{"action":"spawn","name":"x"}'))).toBe('action=spawn · name=x')
  })
})

describe('processOutput', () => {
  it('is the trimmed result text, empty on error', () => {
    expect(processOutput(tool('{"action":"output"}', '{"content":[{"type":"text","text":"line\\n\\n"}]}'))).toBe('line')
    expect(processOutput(tool('{"action":"output"}', '{"content":[{"type":"text","text":"bad"}],"isError":true}'))).toBe('')
  })
})
