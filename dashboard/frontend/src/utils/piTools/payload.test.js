import { describe, it, expect } from 'vitest'
import {
  imageByteSize,
  imageLabel,
  isToolError,
  parseToolArgs,
  parseToolCall,
  parseToolResult,
} from './payload'

describe('parseToolResult', () => {
  it('envelope with one text part', () => {
    expect(parseToolResult('{"content":[{"type":"text","text":"hello"}]}')).toEqual({
      text: 'hello',
      images: [],
      details: null,
      structured: null,
      isError: false,
    })
  })

  it('two text parts join with a newline', () => {
    const result = parseToolResult(
      '{"content":[{"type":"text","text":"first"},{"type":"text","text":"second"}]}',
    )
    expect(result.text).toBe('first\nsecond')
  })

  it('text and image parts are separated', () => {
    const result = parseToolResult(
      '{"content":[{"type":"text","text":"see"},{"type":"image","data":"QUJD","mimeType":"image/png"}]}',
    )
    expect(result.text).toBe('see')
    expect(result.images).toEqual([{ mimeType: 'image/png', base64: 'QUJD' }])
  })

  it('an image without a mime type defaults to png', () => {
    const result = parseToolResult('{"content":[{"type":"image","data":"QUJD"}]}')
    expect(result.images).toEqual([{ mimeType: 'image/png', base64: 'QUJD' }])
  })

  it('envelope keeps structured content, details and the error flag', () => {
    const result = parseToolResult(
      '{"content":[{"type":"text","text":"boom"}],"structuredContent":{"output":"boom","exit_code":1},"details":{"diff":"+a"},"isError":true}',
    )
    expect(result.text).toBe('boom')
    expect(result.structured).toEqual({ output: 'boom', exit_code: 1 })
    expect(result.details).toEqual({ diff: '+a' })
    expect(result.isError).toBe(true)
  })

  it('malformed parts are skipped', () => {
    const result = parseToolResult(
      '{"content":[null,"x",{"type":"text","text":3},{"type":"image"},{"type":"text","text":"ok"}]}',
    )
    expect(result.text).toBe('ok')
    expect(result.images).toEqual([])
  })

  it('json string primitive becomes text', () => {
    expect(parseToolResult('"some text"').text).toBe('some text')
  })

  it('truncated json is returned verbatim', () => {
    const raw = '{"content":[{"type":"text","text":"cut'
    expect(parseToolResult(raw)).toEqual({
      text: raw,
      images: [],
      details: null,
      structured: null,
      isError: false,
    })
  })

  it('object without content is returned verbatim', () => {
    const raw = '{"output":"plain"}'
    const result = parseToolResult(raw)
    expect(result.text).toBe(raw)
    expect(result.structured).toBeNull()
  })

  it('plain text is returned verbatim', () => {
    expect(parseToolResult('total 0\ndrwx').text).toBe('total 0\ndrwx')
  })

  it('null result is null', () => {
    expect(parseToolResult(null)).toBeNull()
    expect(parseToolResult(undefined)).toBeNull()
  })
})

describe('parseToolArgs', () => {
  it('args object is parsed', () => {
    expect(parseToolArgs('{"command":"ls","timeout":30}')).toEqual({ command: 'ls', timeout: 30 })
  })

  it('args that are not an object are rejected', () => {
    expect(parseToolArgs('[1,2]')).toBeNull()
    expect(parseToolArgs('"text"')).toBeNull()
    expect(parseToolArgs('null')).toBeNull()
  })

  it('invalid args json is rejected', () => {
    expect(parseToolArgs('{"command":"ls')).toBeNull()
  })

  it('null args are rejected', () => {
    expect(parseToolArgs(null)).toBeNull()
  })
})

describe('images', () => {
  it('byte size is the decoded length', () => {
    expect(imageByteSize({ mimeType: 'image/png', base64: 'QUJD' })).toBe(3)
    expect(imageByteSize({ mimeType: 'image/png', base64: 'QUI=' })).toBe(2)
    expect(imageByteSize({ mimeType: 'image/png', base64: 'QQ==' })).toBe(1)
  })

  it('label names the type and size', () => {
    expect(imageLabel({ mimeType: 'image/jpeg', base64: 'QUJD' })).toBe('image/jpeg · 3 B')
    expect(imageLabel({ mimeType: 'image/png', base64: 'A'.repeat(4096) })).toBe('image/png · 3 KB')
  })
})

describe('isToolError', () => {
  it('is set by the item status or the result flag', () => {
    const item = (status) => ({ status })
    expect(isToolError({ item: item('error'), result: null })).toBe(true)
    expect(isToolError({ item: item('done'), result: { isError: true } })).toBe(true)
    expect(isToolError({ item: item('done'), result: { isError: false } })).toBe(false)
    expect(isToolError({ item: item('running'), result: null })).toBe(false)
  })
})

describe('parseToolCall', () => {
  it('without a tool parser there is no view', () => {
    expect(parseToolCall('{"a":1}', '"done"', null)).toEqual({
      args: { a: 1 },
      result: parseToolResult('"done"'),
      view: null,
    })
  })

  it('runs the tool parser over the parsed args and result', () => {
    const parse = (args, result) => ({ a: args.a, text: result.text })
    expect(parseToolCall('{"a":1}', '"done"', parse).view).toEqual({ a: 1, text: 'done' })
  })

  it('a tool parser that throws or returns nothing gives no view', () => {
    const throws = () => {
      throw new Error('bad payload')
    }
    expect(parseToolCall('{"a":1}', null, throws).view).toBeNull()
    expect(parseToolCall('{"a":1}', null, () => undefined).view).toBeNull()
  })
})
