import { describe, it, expect } from 'vitest'
import { bashExitCode, bashOutput, bashSummary, parseBash, splitCdPrefix } from './bash'
import { parseToolCall } from './payload'

const success = '{"content":[{"type":"text","text":"ok\\n0\\n"}],"structuredContent":{"output":"ok\\n0\\n"}}'
const failed =
  '{"content":[{"type":"text","text":"ok\\n0\\n\\n\\nCommand exited with code 1"}],' +
  '"structuredContent":{"output":"ok\\n0\\n","truncated":false,"exit_code":1,"wall_time_seconds":3.1},"isError":true}'

function tool(args, output, status = 'done') {
  const item = { id: 't1', name: 'bash', args, output, status, durationMs: 3, truncated: false }
  return { ...parseToolCall(args, output, parseBash), item }
}

describe('splitCdPrefix', () => {
  it('strips a plain, quoted or semicolon cd prefix', () => {
    expect(splitCdPrefix('cd /a && ls')).toEqual({ dir: '/a', command: 'ls' })
    expect(splitCdPrefix("cd '/a b' && ls")).toEqual({ dir: '/a b', command: 'ls' })
    expect(splitCdPrefix('cd "/a b" && ls')).toEqual({ dir: '/a b', command: 'ls' })
    expect(splitCdPrefix('cd /a; ls')).toEqual({ dir: '/a', command: 'ls' })
  })

  it('leaves a command without a prefix, or a bare cd, alone', () => {
    expect(splitCdPrefix('ls')).toEqual({ dir: null, command: 'ls' })
    expect(splitCdPrefix('cd /a')).toEqual({ dir: null, command: 'cd /a' })
  })

  it('strips the prefix of a multi-line command', () => {
    expect(splitCdPrefix('cd /a && ls\nfoo')).toEqual({ dir: '/a', command: 'ls\nfoo' })
  })
})

describe('bash result fields', () => {
  it('reads output and exit code from the envelope', () => {
    expect(bashOutput(tool('{}', success).result)).toBe('ok\n0\n')
    expect(bashExitCode(tool('{}', success).result)).toBeNull()
    expect(bashOutput(tool('{}', failed).result)).toBe('ok\n0\n')
    expect(bashExitCode(tool('{}', failed).result)).toBe(1)
  })

  it('falls back to the result text, and to null without a result', () => {
    expect(bashOutput(tool('{}', '{"content":[{"type":"text","text":"plain"}]}').result)).toBe('plain')
    expect(bashOutput(null)).toBeNull()
    expect(bashExitCode(null)).toBeNull()
  })
})

describe('parseBash', () => {
  it('needs a string command', () => {
    expect(parseBash({ cmd: 'ls' }, null)).toBeNull()
    expect(parseBash(null, null)).toBeNull()
  })

  it('carries the timeout', () => {
    expect(parseBash({ command: 'sleep 60', timeout: 30 }, null)).toMatchObject({ command: 'sleep 60', timeout: 30 })
  })
})

describe('bashSummary', () => {
  it('summarises a successful, failing and running command', () => {
    expect(bashSummary(tool('{"command":"cd /a && ls -la"}', success))).toBe('$ ls -la')
    expect(bashSummary(tool('{"command":"cd /a && ls"}', failed, 'error'))).toBe('$ ls · exit 1')
    expect(bashSummary(tool('{"command":"cd /a && ls"}', null, 'running'))).toBe('$ ls')
  })

  it('marks a timed out command', () => {
    const output = '{"content":[{"type":"text","text":"Command timed out after 30s"}],"isError":true}'
    expect(bashSummary(tool('{"command":"sleep 60","timeout":30}', output, 'error'))).toBe('$ sleep 60 · timed out')
  })
})
