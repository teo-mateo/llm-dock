import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, cleanup, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ChatPage from './ChatPage'

// Stub the heavy presentational children — this test is about the
// data/effect wiring in ChatPage, not what the sidebar/area render.
// The sidebar stub captures its props so tests can drive the handlers
// ChatPage wires into it (delete → project-count refresh, etc.).
const { sidebarProps } = vi.hoisted(() => ({ sidebarProps: { current: null } }))
vi.mock('./ChatSidebar', () => ({
  default: (props) => { sidebarProps.current = props; return null },
}))
vi.mock('./ChatArea', () => ({ default: () => null }))

// Running services come from an SSE hook; give it one model so the page
// behaves as a normal authenticated session.
vi.mock('../../hooks/useServicesSSE', () => ({
  default: () => ({ services: [{ name: 'vllm-test', kind: 'chat' }], loading: false }),
}))

const { mockGetConversation, mockListConversations, mockCancelActiveRun,
        mockListProjects, mockDeleteConversation, mockDeleteConversations } = vi.hoisted(() => ({
  mockGetConversation: vi.fn(),
  mockListConversations: vi.fn(),
  mockCancelActiveRun: vi.fn(),
  mockListProjects: vi.fn(),
  mockDeleteConversation: vi.fn(),
  mockDeleteConversations: vi.fn(),
}))
vi.mock('../../services/chat', async (importActual) => ({
  ...(await importActual()),
  getConversation: (...a) => mockGetConversation(...a),
  listConversations: (...a) => mockListConversations(...a),
  cancelActiveRun: (...a) => mockCancelActiveRun(...a),
  listProjects: (...a) => mockListProjects(...a),
  deleteConversation: (...a) => mockDeleteConversation(...a),
  deleteConversations: (...a) => mockDeleteConversations(...a),
}))

// streamChat is never expected to fire here (no active run), but stub it to a
// pending promise so an accidental call can't crash the test.
const { mockStreamChat } = vi.hoisted(() => ({ mockStreamChat: vi.fn() }))
vi.mock('../../services/sse', () => ({ streamChat: (...a) => mockStreamChat(...a) }))

beforeEach(() => {
  mockGetConversation.mockReset()
  mockListConversations.mockReset()
  mockStreamChat.mockReset()
  mockGetConversation.mockResolvedValue({
    id: 'abc', title: 'T', main_service: 'vllm-test',
    messages: [], active_run: null, last_run: null,
  })
  mockListConversations.mockResolvedValue({ conversations: [] })
  mockListProjects.mockReset()
  mockListProjects.mockResolvedValue({ projects: [] })
  mockDeleteConversation.mockReset()
  mockDeleteConversation.mockResolvedValue({ ok: true })
  mockDeleteConversations.mockReset()
  mockDeleteConversations.mockResolvedValue({ ok: true, deleted: 1 })
  mockStreamChat.mockImplementation(() => new Promise(() => {}))
  sidebarProps.current = null
})

afterEach(() => cleanup())

describe('ChatPage URL-load effect', () => {
  it('loads the route conversation exactly once across parent rerenders', async () => {
    // Regression for codex iteration 3 P1 on PR #69: ChatPage builds a fresh
    // onConversationUpdated callback every render. The reattach work made
    // loadConversation depend (transitively) on that callback; if it changed
    // identity each render, the URL-load effect ([convId, loadConversation])
    // would re-fire on every rerender and reload in a loop. useChat now holds
    // the callback behind a ref so loadConversation stays stable.
    // `tick` is ignored by the component; bumping it just forces the parent
    // (and thus ChatPage) to re-render, re-running ChatPage's body and
    // rebuilding the inline onConversationUpdated each time.
    function Harness({ tick }) { // eslint-disable-line no-unused-vars
      return (
        <MemoryRouter initialEntries={['/chat/abc']}>
          <Routes>
            <Route path="/chat/:conversationId" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      )
    }

    const { rerender } = render(<Harness tick={0} />)
    await waitFor(() => expect(mockGetConversation).toHaveBeenCalledTimes(1))

    // Force several parent rerenders. A stable loadConversation means the
    // URL-load effect does not re-fire.
    for (let i = 1; i <= 3; i++) {
      await act(async () => { rerender(<Harness tick={i} />) })
    }

    // Give any spurious effect re-runs a chance to land before asserting.
    await new Promise((r) => setTimeout(r, 0))
    expect(mockGetConversation).toHaveBeenCalledTimes(1)
    expect(mockGetConversation).toHaveBeenCalledWith('abc')
  })
})

describe('ChatPage delete → project count refresh', () => {
  function renderPage() {
    return render(
      <MemoryRouter initialEntries={['/chat']}>
        <Routes>
          <Route path="/chat" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    )
  }

  it('refreshes projects after a single conversation delete', async () => {
    // Regression for codex iteration 3 on PR #77: deleting a project's
    // conversation must refetch the cached per-project counts, or the
    // sidebar keeps claiming chats the project no longer has.
    renderPage()
    await waitFor(() => expect(mockListProjects).toHaveBeenCalledTimes(1))

    await act(async () => { await sidebarProps.current.onDelete('c1') })

    expect(mockDeleteConversation).toHaveBeenCalledWith('c1')
    expect(mockListProjects).toHaveBeenCalledTimes(2)
  })

  it('refreshes projects after a bulk conversation delete', async () => {
    renderPage()
    await waitFor(() => expect(mockListProjects).toHaveBeenCalledTimes(1))

    await act(async () => { await sidebarProps.current.onDeleteMany(['c1', 'c2']) })

    expect(mockDeleteConversations).toHaveBeenCalledWith(['c1', 'c2'])
    expect(mockListProjects).toHaveBeenCalledTimes(2)
  })
})
