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

describe('needs-answer indicator', () => {
  it('marks a live session with an open question', () => {
    setup({ sessions: [session({ prompts: [{ prompt_id: 'a' }] })] })
    expect(screen.getByText('1 question waiting')).toBeInTheDocument()
  })

  it('counts several open questions', () => {
    setup({ sessions: [session({ prompts: [{ prompt_id: 'a' }, { prompt_id: 'b' }] })] })
    expect(screen.getByText('2 questions waiting')).toBeInTheDocument()
  })

  it('says nothing for a session with no questions', () => {
    setup({ sessions: [session()] })
    expect(screen.queryByText(/question waiting/i)).not.toBeInTheDocument()
  })

  it('says nothing for an ended session that still has a stored question', () => {
    setup({ sessions: [session({ live: false, prompts: [{ prompt_id: 'a' }] })] })
    expect(screen.queryByText(/question waiting/i)).not.toBeInTheDocument()
  })
})
