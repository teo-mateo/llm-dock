import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import PiToolDetails from './PiToolDetails'
import { parseToolArgs, parseToolResult } from '../../utils/piTools/payload'

function tool(overrides = {}) {
  const item = {
    kind: 'tool',
    id: 'tc1',
    callId: 'c1',
    name: 'web_search',
    args: null,
    output: null,
    status: 'running',
    durationMs: null,
    truncated: false,
    ts: 1000,
    ...overrides,
  }
  return { item, args: parseToolArgs(item.args), result: parseToolResult(item.output) }
}

afterEach(cleanup)

describe('PiToolDetails', () => {
  it('running status', () => {
    render(<PiToolDetails tool={tool()} />)
    expect(screen.getByText('running…')).toBeInTheDocument()
  })

  it('done shows seconds', () => {
    render(<PiToolDetails tool={tool({ status: 'done', durationMs: 1400, output: 'ok' })} />)
    expect(screen.getByText('done · 1.4 s')).toBeInTheDocument()
  })

  it('error status and text', () => {
    render(<PiToolDetails tool={tool({ status: 'error', output: 'boom' })} />)
    expect(screen.getByText('error')).toBeInTheDocument()
    expect(screen.getByText('boom')).toHaveClass('text-danger-fg')
  })

  it('a tool without its own viewer gets the generic body', () => {
    render(
      <PiToolDetails
        tool={tool({
          status: 'done',
          args: '{"query":"tailwind","count":5}',
          output: '{"content":[{"type":"text","text":"1. result"}]}',
        })}
      />,
    )
    expect(screen.getByText('query')).toBeInTheDocument()
    expect(screen.getByText('tailwind')).toBeInTheDocument()
    expect(screen.getByText('1. result')).toBeInTheDocument()
    expect(screen.queryByText(/"content"/)).not.toBeInTheDocument()
  })

  it('a tool named like an object property opens in the generic view', () => {
    for (const name of ['toString', 'constructor', '__proto__']) {
      render(<PiToolDetails tool={tool({ name, status: 'done', output: 'ok' })} />)
      expect(screen.getByText('ok')).toBeInTheDocument()
      cleanup()
    }
  })

  it('raw toggle shows the payload as sent and back', () => {
    const output = '{"content":[{"type":"text","text":"1. result"}]}'
    render(<PiToolDetails tool={tool({ status: 'done', args: '{"q":1}', output })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Raw ▸' }))
    expect(screen.getByText(output)).toBeInTheDocument()
    expect(screen.getByText('{"q":1}')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Formatted ▸' }))
    expect(screen.queryByText(output)).not.toBeInTheDocument()
  })

  it('long output collapsed with show all', () => {
    const output = Array.from({ length: 21 }, (_, index) => `line ${index + 1}`).join('\n')
    render(<PiToolDetails tool={tool({ status: 'done', output })} />)
    expect(screen.queryByText(/line 21/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all 21 lines' }))
    expect(screen.getByText(/line 21/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show less' })).toBeInTheDocument()
  })

  it('truncated note', () => {
    render(<PiToolDetails tool={tool({ status: 'done', truncated: true, output: 'ok' })} />)
    expect(screen.getByText('output truncated by pi-remote')).toBeInTheDocument()
  })
})
