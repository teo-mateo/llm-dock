import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import PiSessionHeader from './PiSessionHeader'

function summary(overrides = {}) {
  return {
    session_id: 's1',
    instance_id: 'i1',
    name: 'llm-dock',
    cwd: '/github/teo-mateo/llm-dock',
    model: 'maya-v149-deepseek-v41-flash',
    thinking_level: 'xhigh',
    live: true,
    state: 'working',
    context_percent: 22,
    ended_at: null,
    end_reason: null,
    ...overrides,
  }
}

afterEach(cleanup)

describe('PiSessionHeader', () => {
  it('shows model and context', () => {
    render(<PiSessionHeader summary={summary({ context_percent: 22.5 })} />)
    expect(screen.getByText('working')).toBeInTheDocument()
    expect(screen.getByText(/maya-v149-deepseek-v41-flash/)).toBeInTheDocument()
    expect(screen.getByText('ctx 23%')).toBeInTheDocument()
  })

  it('hides context bar when unknown', () => {
    render(<PiSessionHeader summary={summary({ context_percent: null })} />)
    expect(screen.queryByText(/^ctx /)).not.toBeInTheDocument()
  })

  it('ended shows end reason', () => {
    render(
      <PiSessionHeader
        summary={summary({
          live: false,
          state: null,
          context_percent: null,
          end_reason: 'dashboard_restart',
        })}
      />,
    )
    expect(screen.getByText('ended')).toBeInTheDocument()
    expect(screen.getByText('dashboard_restart')).toBeInTheDocument()
  })
})
