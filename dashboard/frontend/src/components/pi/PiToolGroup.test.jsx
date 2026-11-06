import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import PiToolGroup from './PiToolGroup'

function tool(id, overrides = {}) {
  return {
    kind: 'tool',
    id: `t${id}`,
    callId: `c${id}`,
    name: 'search_emails',
    args: '{"account":"me"}',
    output: `result ${id}`,
    status: 'done',
    durationMs: 1200,
    truncated: false,
    ts: 1000,
    ...overrides,
  }
}

const group = (tools) => ({ kind: 'tool_group', id: 'g1', tools })

afterEach(cleanup)

describe('PiToolGroup', () => {
  it('one row per tool with name and args summary', () => {
    render(<PiToolGroup group={group([tool(1), tool(2, { name: 'move_emails' })])} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('move_emails')).toBeInTheDocument()
    expect(screen.getAllByText('account=me')).toHaveLength(2)
  })

  it('output is collapsed until details is opened', () => {
    render(<PiToolGroup group={group([tool(1)])} />)
    expect(screen.queryByText('result 1')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Details' }))
    expect(screen.getByText('result 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Details' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('status is announced on the dot', () => {
    render(<PiToolGroup group={group([tool(1, { status: 'error' })])} />)
    expect(screen.getByRole('img', { name: 'error' })).toBeInTheDocument()
  })

  it('long runs collapse after three rows until more is tapped', () => {
    render(<PiToolGroup group={group([1, 2, 3, 4, 5].map((id) => tool(id)))} />)
    expect(screen.getAllByRole('button', { name: 'Details' })).toHaveLength(3)
    fireEvent.click(screen.getByRole('button', { name: '2 more…' }))
    expect(screen.getAllByRole('button', { name: 'Details' })).toHaveLength(5)
    expect(screen.queryByText('2 more…')).not.toBeInTheDocument()
  })
})
