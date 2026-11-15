import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import GenericToolBody from './GenericToolBody'
import { parseToolArgs, parseToolResult } from '../../../utils/piTools/payload'

function tool(args, output, status = 'done') {
  const item = { id: 't1', name: 'x', args, output, status, durationMs: null, truncated: false }
  return { item, args: parseToolArgs(args), result: parseToolResult(output) }
}

afterEach(cleanup)

describe('GenericToolBody', () => {
  it('object args render as a key/value grid', () => {
    render(<GenericToolBody tool={tool('{"path":"/a/b","nested":{"x":1}}', null)} />)
    expect(screen.getByText('path')).toBeInTheDocument()
    expect(screen.getByText('/a/b')).toBeInTheDocument()
    expect(screen.getByText('nested')).toBeInTheDocument()
    expect(screen.getByText(/"x": 1/)).toBeInTheDocument()
  })

  it('args that are not an object render as text', () => {
    render(<GenericToolBody tool={tool('{"cut', null)} />)
    expect(screen.getByText('{"cut')).toBeInTheDocument()
  })

  it('error results are tinted', () => {
    render(<GenericToolBody tool={tool(null, '{"content":[{"type":"text","text":"no"}],"isError":true}')} />)
    expect(screen.getByText('no')).toHaveClass('text-danger-fg')
  })

  it('an empty envelope falls back to the raw output', () => {
    render(<GenericToolBody tool={tool(null, '{"content":[]}')} />)
    expect(screen.getByText('{"content":[]}')).toBeInTheDocument()
  })

  it('images are listed by type and size', () => {
    render(<GenericToolBody tool={tool(null, '{"content":[{"type":"image","data":"QUJD","mimeType":"image/png"}]}')} />)
    expect(screen.getByText('image/png · 3 B')).toBeInTheDocument()
  })

  it('a running call with nothing yet shows only its status', () => {
    render(<GenericToolBody tool={tool(null, null, 'running')} />)
    expect(screen.getByText('running…')).toBeInTheDocument()
  })
})
