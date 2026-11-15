import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import ReadToolBody from './ReadToolBody'
import { parseRead } from '../../../utils/piTools/files'
import { parseToolCall } from '../../../utils/piTools/payload'

function tool(args, output, status = 'done') {
  const item = { id: 't1', name: 'read', args, output, status, durationMs: 3, truncated: false }
  return { ...parseToolCall(args, output, parseRead), item }
}

afterEach(cleanup)

describe('ReadToolBody', () => {
  it('shows the path, the range and lines numbered from the offset', () => {
    const output = '{"content":[{"type":"text","text":"first\\nsecond"}]}'
    render(<ReadToolBody tool={tool('{"path":"/a/b/c.js","offset":40,"limit":2}', output)} />)
    expect(screen.getByText('c.js')).toBeInTheDocument()
    expect(screen.getByText('lines 40–41')).toBeInTheDocument()
    expect(screen.getByText('40')).toBeInTheDocument()
    expect(screen.getByText('second')).toBeInTheDocument()
  })

  it('an image result shows a thumbnail linking to the full image', () => {
    const output =
      '{"content":[{"type":"text","text":"Read image file [image/png]"},{"type":"image","data":"QUJD","mimeType":"image/png"}]}'
    render(<ReadToolBody tool={tool('{"path":"/a/shot.png"}', output)} />)
    const img = screen.getByRole('img', { name: 'image/png · 3 B' })
    expect(img).toHaveAttribute('src', 'data:image/png;base64,QUJD')
    URL.createObjectURL = vi.fn(() => 'blob:full')
    URL.revokeObjectURL = vi.fn()
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    fireEvent.click(img)
    expect(URL.createObjectURL.mock.calls[0][0].type).toBe('image/png')
    expect(open).toHaveBeenCalledWith('blob:full', '_blank', 'noopener')
    open.mockRestore()
    expect(screen.queryByText('Read image file [image/png]')).toBeNull()
  })

  it('an image type that is not previewable shows only its label', () => {
    const output = '{"content":[{"type":"image","data":"QUJD","mimeType":"image/svg+xml"}]}'
    render(<ReadToolBody tool={tool('{"path":"/a/x.svg"}', output)} />)
    expect(screen.queryByRole('img')).toBeNull()
    expect(screen.getByText('image/svg+xml · 3 B')).toBeInTheDocument()
  })

  it('an error shows the message instead of content', () => {
    const output = '{"content":[{"type":"text","text":"ENOENT: no such file"}],"isError":true}'
    render(<ReadToolBody tool={tool('{"path":"/a/missing.js"}', output, 'error')} />)
    expect(screen.getByText('ENOENT: no such file')).toHaveClass('text-danger-fg')
    expect(screen.queryByText('1')).toBeNull()
  })
})
