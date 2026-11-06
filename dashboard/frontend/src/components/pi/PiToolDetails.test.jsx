import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import PiToolDetails from './PiToolDetails'

function tool(overrides = {}) {
  return {
    kind: 'tool',
    id: 'tc1',
    callId: 'c1',
    name: 'bash',
    args: null,
    output: null,
    status: 'running',
    durationMs: null,
    truncated: false,
    ts: 1000,
    ...overrides,
  }
}

afterEach(cleanup)

describe('PiToolDetails', () => {
  it('running status', () => {
    render(<PiToolDetails item={tool()} />)
    expect(screen.getByText('running…')).toBeInTheDocument()
  })

  it('done shows seconds', () => {
    render(<PiToolDetails item={tool({ status: 'done', durationMs: 1400, output: 'ok' })} />)
    expect(screen.getByText('done · 1.4 s')).toBeInTheDocument()
  })

  it('error status', () => {
    render(<PiToolDetails item={tool({ status: 'error', output: 'boom' })} />)
    expect(screen.getByText('error')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
  })

  it('long output collapsed with show all', () => {
    const output = Array.from({ length: 21 }, (_, index) => `line ${index + 1}`).join('\n')
    render(<PiToolDetails item={tool({ status: 'done', output })} />)
    expect(screen.getByText('Show all')).toBeInTheDocument()
    expect(screen.queryByText('line 21')).not.toBeInTheDocument()
  })

  it('truncated note', () => {
    render(<PiToolDetails item={tool({ status: 'done', truncated: true, output: 'ok' })} />)
    expect(screen.getByText('output truncated by pi-remote')).toBeInTheDocument()
  })
})
