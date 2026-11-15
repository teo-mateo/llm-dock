import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import ChatterboxSendBody from './ChatterboxSendBody'
import { parseSend } from '../../../utils/piTools/chatterbox'
import { parseToolCall } from '../../../utils/piTools/payload'

function tool(args, output, status = 'done') {
  const item = { id: 't1', name: 'chatterbox_send', args, output, status, durationMs: 3, truncated: false }
  return { ...parseToolCall(args, output, parseSend), item }
}

afterEach(cleanup)

describe('ChatterboxSendBody', () => {
  it('shows target, private and confirmed chips and the text in a bubble', () => {
    const output = '{"content":[{"type":"text","text":"Sent privately to po; confirmed."}],"details":{"outcome":"confirmed"}}'
    render(<ChatterboxSendBody tool={tool('{"audience":"private","to":"po","text":"Ready for review."}', output)} />)
    expect(screen.getByText('→ po')).toBeInTheDocument()
    expect(screen.getByText('private')).toBeInTheDocument()
    expect(screen.getByText('confirmed')).toHaveClass('text-success-fg')
    expect(screen.getByText('Ready for review.')).toHaveClass('rounded-lg')
    expect(screen.queryByText('Sent privately to po; confirmed.')).toBeNull()
  })

  it('explains a held-back send', () => {
    const output = '{"content":[{"type":"text","text":"NOT SENT. 1 item arrived."}],"details":{"outcome":"held-back"}}'
    render(<ChatterboxSendBody tool={tool('{"audience":"participant","to":"po","text":"x"}', output)} />)
    expect(screen.getByText('held-back')).toHaveClass('text-warning-fg')
    expect(screen.getByText('NOT SENT. 1 item arrived.')).toBeInTheDocument()
  })

  it('shows a rejected send in red', () => {
    const output = '{"content":[{"type":"text","text":"audience \'participant\' needs \'to\'"}],"isError":true}'
    render(<ChatterboxSendBody tool={tool('{"audience":"participant","text":"x"}', output, 'error')} />)
    expect(screen.getByText("audience 'participant' needs 'to'")).toHaveClass('text-danger-fg')
  })
})
