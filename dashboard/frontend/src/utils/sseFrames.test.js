import { describe, it, expect } from 'vitest'
import { createSseParser } from './sseFrames'

describe('createSseParser', () => {
  it('parses event, id and data', () => {
    const parser = createSseParser()
    expect(parser.push('event: session\nid: 5\ndata: {"a":1}\n\n')).toEqual([
      { event: 'session', id: '5', data: '{"a":1}' },
    ])
  })

  it('ignores keepalive comments', () => {
    const parser = createSseParser()
    expect(parser.push(': keepalive\n\n')).toEqual([])
  })

  it('joins multi-line data', () => {
    const parser = createSseParser()
    expect(parser.push('data: first\ndata: second\n\n')).toEqual([
      { event: 'message', id: null, data: 'first\nsecond' },
    ])
  })

  it('handles a frame split across chunks', () => {
    const parser = createSseParser()
    expect(parser.push('event: events\nid: 1\nda')).toEqual([])
    expect(parser.push('ta: {}\n\n')).toEqual([
      { event: 'events', id: '1', data: '{}' },
    ])
  })

  it('handles CRLF', () => {
    const parser = createSseParser()
    expect(parser.push('event: x\r\nid: 2\r\ndata: y\r\n\r\n')).toEqual([
      { event: 'x', id: '2', data: 'y' },
    ])
  })

  it('defaults event to message', () => {
    const parser = createSseParser()
    expect(parser.push('id: 9\ndata: z\n\n')).toEqual([
      { event: 'message', id: '9', data: 'z' },
    ])
  })
})
