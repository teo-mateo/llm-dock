import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import BashToolBody from './BashToolBody'
import { parseBash } from '../../../utils/piTools/bash'
import { parseToolCall } from '../../../utils/piTools/payload'

function tool(args, output, status = 'done') {
  const item = { id: 't1', name: 'bash', args, output, status, durationMs: 4200, truncated: false }
  return { ...parseToolCall(args, output, parseBash), item }
}

const failed =
  '{"content":[{"type":"text","text":"boom"}],"structuredContent":{"output":"boom","exit_code":2},"isError":true}'

afterEach(cleanup)

describe('BashToolBody', () => {
  it('shows the stripped dir, the timeout and the command behind a prompt', () => {
    render(<BashToolBody tool={tool('{"command":"cd /repo && npm test","timeout":120}', null, 'running')} />)
    expect(screen.getByText('📁 /repo')).toBeInTheDocument()
    expect(screen.getByText('timeout 120 s')).toBeInTheDocument()
    expect(screen.getByText('$')).toHaveClass('select-none')
    expect(screen.getByText('npm test')).toBeInTheDocument()
  })

  it('a failure shows its exit code and output', () => {
    render(<BashToolBody tool={tool('{"command":"false"}', failed, 'error')} />)
    expect(screen.getByText('exit 2')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it('a zero exit is not shown and empty output says so', () => {
    const ok = '{"content":[],"structuredContent":{"output":"","exit_code":0}}'
    render(<BashToolBody tool={tool('{"command":"true"}', ok)} />)
    expect(screen.queryByText('exit 0')).toBeNull()
    expect(screen.getByText('(no output)')).toBeInTheDocument()
  })

  it('a timeout is shown as a chip', () => {
    const output = '{"content":[{"type":"text","text":"Command timed out after 30s"}],"isError":true}'
    render(<BashToolBody tool={tool('{"command":"sleep 60"}', output, 'error')} />)
    expect(screen.getByText('timed out')).toBeInTheDocument()
  })
})
