import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import WriteToolBody from './WriteToolBody'
import { parseWrite } from '../../../utils/piTools/files'
import { parseToolCall } from '../../../utils/piTools/payload'

function tool(output, status = 'done') {
  const args = '{"path":"/a/b/new.js","content":"one\\ntwo\\n"}'
  const item = { id: 't1', name: 'write', args, output, status, durationMs: 3, truncated: false }
  return { ...parseToolCall(args, output, parseWrite), item }
}

afterEach(cleanup)

describe('WriteToolBody', () => {
  it('numbers the written content and counts its lines', () => {
    render(<WriteToolBody tool={tool('{"content":[{"type":"text","text":"Successfully wrote 8 bytes"}]}')} />)
    expect(screen.getByText('new.js')).toBeInTheDocument()
    expect(screen.getByText('2 lines')).toBeInTheDocument()
    expect(screen.getByText('two')).toBeInTheDocument()
    expect(screen.getByText('Successfully wrote 8 bytes')).toHaveClass('text-fg-muted')
  })

  it('an error is shown in red', () => {
    render(<WriteToolBody tool={tool('{"content":[{"type":"text","text":"EACCES"}],"isError":true}', 'error')} />)
    expect(screen.getByText('EACCES')).toHaveClass('text-danger-fg')
  })
})
