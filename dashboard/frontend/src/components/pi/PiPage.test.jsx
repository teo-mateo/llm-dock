import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import PiPage from './PiPage'
import { usePiSessions } from '../../hooks/usePiSessions'
import { usePiSessionEvents } from '../../hooks/usePiSessionEvents'
import { abortPiRun, answerPiPrompt } from '../../services/piRemote'

vi.mock('../../hooks/usePiSessions', () => ({ usePiSessions: vi.fn() }))
vi.mock('../../hooks/usePiSessionEvents', () => ({ usePiSessionEvents: vi.fn() }))
vi.mock('../../services/piRemote', () => ({
  sendPiMessage: vi.fn(),
  abortPiRun: vi.fn(),
  answerPiPrompt: vi.fn(),
}))

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
  abortPiRun.mockReset()
  abortPiRun.mockResolvedValue({
    status: 200,
    body: { command_id: 'cmd-1', ok: true, error: null },
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('PiPage', () => {
  it('no selection prompt', () => {
    usePiSessions.mockReturnValue({ sessions: [session()], connected: true, error: null })
    renderPage('/pi')
    expect(screen.getByText('Pick a session to watch it here.')).toBeInTheDocument()
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

  it('stop then run_end error renders stopped', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(1000)
    usePiSessionEvents.mockReturnValue({
      events: [
        {
          seq: 1,
          type: 'state',
          ts: 1000,
          payload: { state: 'working' },
        },
        {
          seq: 2,
          type: 'run_end',
          ts: 2000,
          payload: { outcome: 'error' },
        },
      ],
      summary: session({ state: 'working', live: true }),
      connected: true,
      error: null,
    })
    renderPage('/pi/s1/i1')
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    await screen.findByText('stopped')
    expect(abortPiRun).toHaveBeenCalledWith('s1', 'i1')
  })
})

describe('pi prompt cards', () => {
  beforeEach(() => {
    answerPiPrompt.mockReset()
    answerPiPrompt.mockResolvedValue({ status: 200, body: { ok: true, prompt_id: 'call-1' } })
  })

  it('shows an open question above the transcript and answers it', async () => {
    usePiSessionEvents.mockReturnValue({
      events: [],
      summary: session({ prompts: [{ prompt_id: 'call-1', kind: 'confirm', title: 'Deploy?', message: '', options: [], allow_free_text: false, timeout_ms: null }] }),
      connected: true,
      error: null,
    })
    renderPage('/pi/s1/i1')
    fireEvent.click(await screen.findByRole('button', { name: 'Yes' }))
    await waitFor(() => expect(answerPiPrompt).toHaveBeenCalledWith('s1', 'i1', 'call-1', true))
  })

  it('disappears when the session frame closes the question', async () => {
    usePiSessionEvents.mockReturnValue({
      events: [],
      summary: session({ prompts: [{ prompt_id: 'call-1', kind: 'select', title: 'Which colour', message: '', options: ['red'], allow_free_text: false, timeout_ms: null }] }),
      connected: true,
      error: null,
    })
    const { rerender } = render(
      <MemoryRouter initialEntries={['/pi/s1/i1']}>
        <Routes>
          <Route path="/pi/:sessionId?/:instanceId?" element={<PiPage />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByRole('button', { name: 'red' })).toBeInTheDocument()
    usePiSessionEvents.mockReturnValue({
      events: [],
      summary: session({ prompts: [] }),
      connected: true,
      error: null,
    })
    rerender(
      <MemoryRouter initialEntries={['/pi/s1/i1']}>
        <Routes>
          <Route path="/pi/:sessionId?/:instanceId?" element={<PiPage />} />
        </Routes>
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.queryByRole('button', { name: 'red' })).not.toBeInTheDocument())
  })
})

  it('keeps a bounded stack of many questions above the composer', () => {
    const many = ['a', 'b', 'c'].map((id) => ({
      prompt_id: `p-${id}`,
      kind: 'select',
      title: `Question ${id}`,
      message: 'x'.repeat(600),
      options: ['one', 'two', 'three', 'four', 'five', 'six'],
      allow_free_text: false,
      timeout_ms: null,
    }))
    usePiSessionEvents.mockReturnValue({
      events: [],
      summary: session({ prompts: many }),
      connected: true,
      error: null,
    })
    renderPage('/pi/s1/i1')
    const stack = screen.getByTestId('pi-prompt-stack')
    expect(stack).toHaveClass('overflow-y-auto')
    expect(stack).toHaveClass('shrink-0')
    expect(stack).toHaveTextContent('3 questions need an answer')
    expect(screen.getByText('Question a')).toBeInTheDocument()
    expect(screen.getByText('Question c')).toBeInTheDocument()
    expect(screen.getByLabelText('Message to pi')).toBeInTheDocument()
    expect(stack.compareDocumentPosition(screen.getByLabelText('Message to pi')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows no header line and no stack when nothing is open', () => {
    usePiSessionEvents.mockReturnValue({
      events: [],
      summary: session({ prompts: [] }),
      connected: true,
      error: null,
    })
    renderPage('/pi/s1/i1')
    expect(screen.queryByTestId('pi-prompt-stack')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Message to pi')).toBeInTheDocument()
  })

describe('list column layout', () => {
  it('keeps the card column narrow and lets the page use the full width', () => {
    renderPage('/pi')
    const aside = document.querySelector('aside')
    expect(aside.className).toContain('md:w-60')
    expect(aside.className).not.toContain('md:w-72')
    const page = aside.parentElement
    expect(page.className).toContain('w-full')
    expect(page.className).not.toContain('max-w-6xl')
    expect(page.className).toContain('min-w-0')
  })
})
