import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import EditToolBody from './EditToolBody'
import { parseEdit } from '../../../utils/piTools/edit'
import { parseToolCall } from '../../../utils/piTools/payload'

const args = '{"path":"/repo/src/api.ts","edits":[{"oldText":"old","newText":"new"}]}'
const patch = '--- a/api.ts\n+++ b/api.ts\n@@ -7,3 +7,3 @@\n keep\n-gone\n+added\n tail'

function tool(output, status = 'done') {
  const item = { id: 't1', name: 'edit', args, output, status, durationMs: 0, truncated: false }
  return { ...parseToolCall(args, output, parseEdit), item }
}

afterEach(cleanup)

describe('EditToolBody', () => {
  it('renders the patch as a numbered diff with counts', () => {
    const output = JSON.stringify({ content: [{ type: 'text', text: 'ok' }], details: { patch } })
    const { container } = render(<EditToolBody tool={tool(output)} />)
    expect(screen.getByText('/repo/src/')).toBeInTheDocument()
    expect(screen.getByText('api.ts')).toBeInTheDocument()
    expect(screen.getByText('+1')).toBeInTheDocument()
    expect(screen.getByText('−1')).toBeInTheDocument()
    expect(screen.getByText('@@ -7,3 +7,3 @@')).toBeInTheDocument()
    expect(screen.getByText('gone').closest('[data-kind]')).toHaveClass('bg-danger-subtle')
    expect(screen.getByText('added').closest('[data-kind]')).toHaveClass('bg-success-subtle')
    const numbers = [...container.querySelectorAll('[data-kind] > span:first-child')].map((node) => node.textContent)
    expect(numbers).toEqual(['⋯', '7', '8', '8', '9'])
  })

  it('without a patch builds the diff from the edits and shows no counts', () => {
    render(<EditToolBody tool={tool(null, 'running')} />)
    expect(screen.getByText('edit 1')).toBeInTheDocument()
    expect(screen.getByText('old')).toBeInTheDocument()
    expect(screen.getByText('new')).toBeInTheDocument()
    expect(screen.queryByText(/^\+\d/)).toBeNull()
  })

  it('a failure shows the error instead of the diff', () => {
    const output = '{"content":[{"type":"text","text":"Could not find the exact text"}],"isError":true}'
    render(<EditToolBody tool={tool(output, 'error')} />)
    expect(screen.getByText('Could not find the exact text')).toHaveClass('text-danger-fg')
    expect(screen.queryByText('edit 1')).toBeNull()
  })
})
