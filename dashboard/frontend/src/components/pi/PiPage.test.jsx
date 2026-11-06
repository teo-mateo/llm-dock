import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import PiPage from './PiPage'
import { usePiSessions } from '../../hooks/usePiSessions'
import { usePiSessionEvents } from '../../hooks/usePiSessionEvents'

vi.mock('../../hooks/usePiSessions', () => ({ usePiSessions: vi.fn() }))
vi.mock('../../hooks/usePiSessionEvents', () => ({ usePiSessionEvents: vi.fn() }))

function session(overrides = {}) {
  return {
    session_id: 's1',
    instance_id: 'i1',
    name: 'llm-dock',
    cwd: '/github/teo-mateo/llm-dock',
    model: 'maya-v149-deepseek-v41-flash',
    thinking_level: 'xhigh',
    state: 'working',
    live: true,
    context_percent: 22,
    ...overrides,
  }
}

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

function renderPage(path) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/pi/:sessionId?/:instanceId?" element={<PiPage />} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  usePiSessions.mockReturnValue({ sessions: [], connected: true, error: null })
  usePiSessionEvents.mockReturnValue({
    events: [],
    summary: null,
    connected: true,
    error: null,
  })
})

afterEach(cleanup)

describe('PiPage', () => {
  it('no selection prompt', () => {
    usePiSessions.mockReturnValue({ sessions: [session()], connected: true, error: null })
    renderPage('/pi')
    expect(screen.getByText('Select a session')).toBeInTheDocument()
  })

  it('selected session renders transcript items', () => {
    usePiSessionEvents.mockReturnValue({
      events: [
        {
          seq: 1,
          type: 'user_message',
          ts: 1000,
          payload: { text: 'hello pi', image_count: 0, origin: 'terminal' },
        },
      ],
      summary: session(),
      connected: true,
      error: null,
    })
    renderPage('/pi/s1/i1')
    expect(screen.getByText('hello pi')).toBeInTheDocument()
    expect(screen.getByText('working')).toBeInTheDocument()
  })

  it('unknown session message', () => {
    usePiSessionEvents.mockReturnValue({
      events: [],
      summary: null,
      connected: false,
      error: 'unknown_session',
    })
    renderPage('/pi/s1/i1')
    expect(
      screen.getByText('This session is no longer known to the dashboard.'),
    ).toBeInTheDocument()
  })

  it('selecting navigates to the session route', () => {
    const s = session()
    usePiSessions.mockReturnValue({ sessions: [s], connected: true, error: null })
    renderPage('/pi')
    fireEvent.click(screen.getByRole('button', { name: /llm-dock/ }))
    expect(screen.getByTestId('location')).toHaveTextContent('/pi/s1/i1')
  })
})
