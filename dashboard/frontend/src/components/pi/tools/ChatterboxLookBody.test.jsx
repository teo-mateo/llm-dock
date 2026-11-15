import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import ChatterboxLookBody from './ChatterboxLookBody'
import { parseLook } from '../../../utils/piTools/chatterbox'
import { parseToolCall } from '../../../utils/piTools/payload'

function tool(args, output) {
  const item = { id: 't1', name: 'chatterbox_look', args, output, status: 'done', durationMs: 3, truncated: false }
  return { ...parseToolCall(args, output, parseLook), item }
}

function message(overrides) {
  return { time: '2026-11-09T12:41:58Z', from: 'po', kind: 'human', text: 'hello', ...overrides }
}

afterEach(cleanup)

describe('ChatterboxLookBody', () => {
  it('shows one line per message, bots in info blue, addressed and important tinted', () => {
    const output = JSON.stringify({
      content: [{ type: 'text', text: 'duplicate text' }],
      details: {
        items: [
          message({ from: 'architect', kind: 'bot', text: 'bot line' }),
          message({ from: 'teodor', addressed: true, text: 'to you line' }),
          message({ from: 'po', important: true, text: 'urgent line' }),
        ],
      },
    })
    render(<ChatterboxLookBody tool={tool('{"what":"recent"}', output)} />)
    expect(screen.getByText('architect')).toHaveClass('text-info-fg')
    expect(screen.getByText('teodor')).toHaveClass('text-fg')
    expect(screen.getByText('to you line').closest('li')).toHaveClass('bg-accent-subtle')
    expect(screen.getByText('urgent line').closest('li')).toHaveClass('bg-warning-subtle')
    expect(screen.getAllByText('12:41')).toHaveLength(3)
    expect(screen.queryByText('duplicate text')).toBeNull()
  })

  it('caps a long backlog at 20 messages', () => {
    const items = Array.from({ length: 25 }, (_, index) => message({ text: `m${index}` }))
    render(<ChatterboxLookBody tool={tool('{"what":"recent","count":25}', JSON.stringify({ content: [], details: { items } }))} />)
    expect(screen.queryByText('m24')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Show all 25 messages' }))
    expect(screen.getByText('m24')).toBeInTheDocument()
  })

  it('lists people, and falls back to the result text otherwise', () => {
    const who = '{"content":[{"type":"text","text":"x"}],"details":{"people":[{"nick":"architect","kind":"bot"}]}}'
    render(<ChatterboxLookBody tool={tool('{"what":"who"}', who)} />)
    expect(screen.getByText('architect')).toHaveClass('text-info-fg')
    cleanup()
    render(<ChatterboxLookBody tool={tool('{}', '{"content":[{"type":"text","text":"Connected as architect."}]}')} />)
    expect(screen.getByText('look status')).toBeInTheDocument()
    expect(screen.getByText('Connected as architect.')).toBeInTheDocument()
  })
})
