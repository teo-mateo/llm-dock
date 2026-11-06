import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import PiSessionList from './PiSessionList'

function session(overrides = {}) {
  return {
    session_id: 's1',
    instance_id: 'i1',
    name: 'llm-dock',
    cwd: '/github/teo-mateo/llm-dock',
    state: 'working',
    live: true,
    ...overrides,
  }
}

function setup(props = {}) {
  const onSelect = vi.fn()
  const onToggleLiveOnly = vi.fn()
  render(
    <PiSessionList
      sessions={[]}
      selectedKey={null}
      onSelect={onSelect}
      liveOnly={true}
      onToggleLiveOnly={onToggleLiveOnly}
      {...props}
    />,
  )
  return { onSelect, onToggleLiveOnly }
}

afterEach(cleanup)

describe('PiSessionList', () => {
  it('renders label text not only colour', () => {
    setup({ sessions: [session()] })
    expect(screen.getByText('working')).toBeInTheDocument()
    expect(screen.getByText('llm-dock')).toBeInTheDocument()
  })

  it('live only hides ended sessions', () => {
    setup({
      sessions: [
        session({ session_id: 'live', name: 'live', state: 'working', live: true }),
        session({ session_id: 'gone', name: 'old', state: null, live: false }),
      ],
    })
    expect(screen.getByText('live')).toBeInTheDocument()
    expect(screen.queryByText('old')).not.toBeInTheDocument()
  })

  it('empty state', () => {
    setup()
    expect(
      screen.getByText('No pi sessions yet — start pi with the pi-remote extension.'),
    ).toBeInTheDocument()
  })

  it('click selects the session', () => {
    const s = session()
    const { onSelect } = setup({ sessions: [s] })
    fireEvent.click(screen.getByRole('button', { name: /llm-dock/ }))
    expect(onSelect).toHaveBeenCalledWith(s)
  })
})
