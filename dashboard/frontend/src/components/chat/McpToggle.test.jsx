import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import McpToggle from './McpToggle'

// The available-servers list comes from GET /chat/mcp-servers via fetchAPI.
const { mockFetchAPI } = vi.hoisted(() => ({ mockFetchAPI: vi.fn() }))
vi.mock('../../api', () => ({
  fetchAPI: (...args) => mockFetchAPI(...args),
}))

// updateConversation is the persisted-mode side effect we assert is NOT
// taken in controlled mode.
const { mockUpdateConversation } = vi.hoisted(() => ({ mockUpdateConversation: vi.fn() }))
vi.mock('../../services/chat', () => ({
  updateConversation: (...args) => mockUpdateConversation(...args),
}))

const SERVERS = [
  { id: 'sympy-math', name: 'Sympy', description: 'math', icon: 'fa-calculator' },
  { id: 'websearch', name: 'Web', description: 'search', icon: 'fa-globe' },
]

beforeEach(() => {
  mockFetchAPI.mockReset()
  mockUpdateConversation.mockReset()
  mockFetchAPI.mockResolvedValue({ servers: SERVERS })
})

afterEach(() => cleanup())

async function renderToggle(props) {
  render(<McpToggle conversationId="conv-1" enabledServers={[]} {...props} />)
  // Wait for the async server-list fetch to populate the buttons.
  await screen.findByText('Sympy')
}

describe('McpToggle controlled mode (onChange)', () => {
  it('calls onChange with the next server list and does NOT persist', async () => {
    const onChange = vi.fn()
    const onUpdate = vi.fn()
    await renderToggle({ onChange, onUpdate })

    fireEvent.click(screen.getByText('Sympy'))

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith(['sympy-math'])
    // Controlled mode is in-memory only: no PUT to the conversation, and the
    // persisted-mode refetch callback must not fire.
    expect(mockUpdateConversation).not.toHaveBeenCalled()
    expect(onUpdate).not.toHaveBeenCalled()
  })

  it('toggling an already-enabled server hands back the list with it removed', async () => {
    const onChange = vi.fn()
    render(<McpToggle conversationId="conv-1" enabledServers={['sympy-math']} onChange={onChange} />)
    await screen.findByText('Sympy')

    fireEvent.click(screen.getByText('Sympy'))

    expect(onChange).toHaveBeenCalledWith([])
    expect(mockUpdateConversation).not.toHaveBeenCalled()
  })
})

describe('McpToggle persisted mode (no onChange)', () => {
  it('persists via updateConversation and refetches when onChange is absent', async () => {
    const onUpdate = vi.fn()
    mockUpdateConversation.mockResolvedValue({})
    render(<McpToggle conversationId="conv-1" enabledServers={[]} onUpdate={onUpdate} />)
    await screen.findByText('Sympy')

    fireEvent.click(screen.getByText('Sympy'))

    await waitFor(() => expect(mockUpdateConversation).toHaveBeenCalledTimes(1))
    expect(mockUpdateConversation).toHaveBeenCalledWith('conv-1', {
      mcp_servers_json: JSON.stringify(['sympy-math']),
    })
    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1))
  })
})
