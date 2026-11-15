import { describe, it, expect } from 'vitest'
import { parseRead, parseWrite, rangeText, readSummary, writeSummary } from './files'
import { parseToolCall } from './payload'

function tool(name, args, output = null) {
  const parse = name === 'read' ? parseRead : parseWrite
  const item = { id: 't1', name, args, output, status: 'done', durationMs: 3, truncated: false }
  return { ...parseToolCall(args, output, parse), item }
}

describe('rangeText', () => {
  it('names the range, or nothing for a whole file', () => {
    const range = (args) => rangeText(parseRead(args, null))
    expect(range({ offset: 40, limit: 40 })).toBe('lines 40–79')
    expect(range({ offset: 40 })).toBe('from line 40')
    expect(range({ limit: 60 })).toBe('first 60 lines')
    expect(range({})).toBeNull()
  })
})

describe('parseRead', () => {
  it('numbers the result from the offset', () => {
    const output = '{"content":[{"type":"text","text":"a\\nb\\n"}]}'
    expect(tool('read', '{"path":"/x/y.js","offset":120}', output).view.lines).toEqual([
      { number: 120, text: 'a' },
      { number: 121, text: 'b' },
    ])
    expect(tool('read', '{"path":"/x/y.js"}', output).view.lines[0].number).toBe(1)
  })
})

describe('readSummary', () => {
  it('shows the name and the range', () => {
    expect(readSummary(tool('read', '{"path":"/f/wt/AuthFlowTests.cs","offset":120,"limit":60}'))).toBe('AuthFlowTests.cs L120–179')
    expect(readSummary(tool('read', '{"path":"/f/wt/AuthFlowTests.cs","offset":120}'))).toBe('AuthFlowTests.cs L120–')
    expect(readSummary(tool('read', '{"path":"/f/wt/AuthFlowTests.cs"}'))).toBe('AuthFlowTests.cs')
  })

  it('names an image result', () => {
    const output =
      '{"content":[{"type":"text","text":"Read image file [image/png]"},{"type":"image","data":"AAAA","mimeType":"image/png"}]}'
    expect(readSummary(tool('read', '{"path":"/f/wt/screenshot.png"}', output))).toBe('screenshot.png · image')
  })

  it('falls back without a path', () => {
    expect(readSummary(tool('read', '{"limit":60}'))).toBe('limit=60')
  })
})

describe('write', () => {
  it('counts and numbers the content lines', () => {
    const written = tool('write', '{"path":"/f/wt/AccountRules.cs","content":"a\\nb\\n"}')
    expect(writeSummary(written)).toBe('AccountRules.cs · 2 lines')
    expect(written.view.lines).toEqual([
      { number: 1, text: 'a' },
      { number: 2, text: 'b' },
    ])
  })

  it('falls back without a path', () => {
    expect(writeSummary(tool('write', '{"content":"a"}'))).toBe('content=a')
  })
})
