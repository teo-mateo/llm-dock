import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import ChatArea from './ChatArea'

// useRunningServices (pulled in transitively by the empty-state composer's
// ChatInput-less path is fine, but ChatArea itself doesn't use it). We only
// exercise the no-conversation branches here, so no router/hook mocking is
// needed beyond what ChatArea's own imports require.
vi.mock('../../hooks/useRunningServices', () => ({
  default: () => ({ services: [], loading: false }),
}))

// Heavy children that fetch or need extra context — not under test here.
vi.mock('./ModelSelector', () => ({ default: () => null }))
vi.mock('./McpToggle', () => ({ default: () => null }))
vi.mock('./MessageList', () => ({ default: () => null }))

vi.mock('../../hooks/useChatPrompts', () => ({
  default: () => ({
    prompts: [
      { id: 'prompt-1', name: 'Prompt 1', content: 'You are a helpful assistant.', sort_order: 0 },
      { id: 'prompt-2', name: 'Prompt 2', content: 'You are a coding expert.', sort_order: 1 },
    ],
    loading: false,
    error: null,
    refetch: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    reorder: vi.fn(),
  }),
}))

const { mockUpdateConversation } = vi.hoisted(() => ({ mockUpdateConversation: vi.fn() }))
vi.mock('../../services/chat', async (importActual) => ({
  ...(await importActual()),
  updateConversation: (...args) => mockUpdateConversation(...args),
}))

afterEach(() => cleanup())

describe('ChatArea no-conversation states', () => {
  it('shows the create composer when there is no route conversation', () => {
    const { container } = render(
      <ChatArea
        conversation={null}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        onCreateAndSend={() => {}}
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
      />
    )
    expect(container.textContent).toContain('Start a new conversation')
    expect(container.querySelector('textarea')).toBeTruthy()
  })

  it('shows a loading state (no composer) while a URL conversation is fetching', () => {
    // Regression for codex iteration 1 P1: opening /v2/chat/<id> directly
    // leaves `conversation` null during loadConversation — the empty-state
    // composer must NOT render, or typing would create a different chat.
    const { container } = render(
      <ChatArea
        conversation={null}
        awaitingConversation={true}
        defaultModelName="vllm-test"
        onCreateAndSend={() => {}}
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
      />
    )
    expect(container.textContent).toContain('Loading conversation')
    expect(container.textContent).not.toContain('Start a new conversation')
    expect(container.querySelector('textarea')).toBeNull()
  })

  it('shows loading (not the stale chat) when switching to a different route id', () => {
    // Regression for codex iteration 2 P1: loadConversation does not clear
    // the previous conversation before fetching, so when switching from A
    // to B, `conversation` is still A while awaitingConversation is true.
    // awaitingConversation must be authoritative — render loading, not A's
    // composer — or an Enter would send into A via its stale closure.
    const { container } = render(
      <ChatArea
        conversation={{ id: 'conv-A', main_service: 'vllm-test' }}
        awaitingConversation={true}
        defaultModelName="vllm-test"
        onCreateAndSend={() => {}}
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
      />
    )
    expect(container.textContent).toContain('Loading conversation')
    expect(container.querySelector('textarea')).toBeNull()
  })
})

describe('ChatArea — prompt selection', () => {
  // PromptSelector is read-only (no async save), so handleSend no longer
  // needs to flush a pending edit before sending.
  beforeEach(() => {
    mockUpdateConversation.mockReset()
  })

  function renderConversation(mainSystemPrompt = '', onSend) {
    return render(
      <ChatArea
        conversation={{
          id: 'conv-1',
          main_service: 'vllm-test',
          main_system_prompt: mainSystemPrompt,
          mcp_servers: [],
        }}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
        streaming={false}
        onSend={onSend}
      />
    )
  }

  it('shows the selected prompt name in the selector button', () => {
    renderConversation('You are a helpful assistant.', vi.fn())
    expect(screen.getByText('Prompt 1')).toBeTruthy()
  })

  it('shows None when the system prompt does not match any managed prompt', () => {
    renderConversation('custom prompt', vi.fn())
    expect(screen.getByText('None')).toBeTruthy()
  })

  it('selecting a prompt calls updateConversation with its content', () => {
    renderConversation('', vi.fn())

    fireEvent.click(screen.getByRole('button', { name: /System Prompt/ }))
    fireEvent.click(screen.getByRole('radio', { name: /Prompt 1/ }))

    expect(mockUpdateConversation).toHaveBeenCalledWith('conv-1', {
      main_system_prompt: 'You are a helpful assistant.',
    })
  })

  it('selecting None calls updateConversation with empty string', () => {
    renderConversation('You are a helpful assistant.', vi.fn())

    fireEvent.click(screen.getByRole('button', { name: /System Prompt/ }))
    fireEvent.click(screen.getByRole('radio', { name: /^None/ }))

    expect(mockUpdateConversation).toHaveBeenCalledWith('conv-1', {
      main_system_prompt: '',
    })
  })

  it('sends a message immediately without any prompt-save flush', async () => {
    const onSend = vi.fn()
    const { container } = renderConversation('', onSend)

    const composer = container.querySelector('textarea')
    fireEvent.change(composer, { target: { value: 'hello' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('hello', undefined))
  })
})

describe('ChatArea — active background run on return', () => {
  // Regression for codex iteration 7 P2: returning to a conversation whose run
  // is still going (streaming false, but conversation.active_run set) must keep
  // the composer blocked and offer Stop — otherwise the run is uncontrollable
  // and a send just hits the backend 409 active-run guard.
  function renderWith(activeRun, onStopStreaming = () => {}) {
    return render(
      <ChatArea
        conversation={{
          id: 'conv-1',
          main_service: 'vllm-test',
          main_system_prompt: '',
          mcp_servers: [],
          active_run: activeRun,
        }}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
        streaming={false}
        onStopStreaming={onStopStreaming}
      />
    )
  }

  it('disables the composer and shows Stop for a running active_run with no local stream', () => {
    const onStop = vi.fn()
    const { container } = renderWith({ status: 'running' }, onStop)
    expect(container.querySelector('textarea').disabled).toBe(true)
    const stop = screen.getByRole('button', { name: /Stop/ })
    fireEvent.click(stop)
    expect(onStop).toHaveBeenCalledTimes(1)
  })

  it('also blocks for a queued active_run', () => {
    const { container } = renderWith({ status: 'queued' })
    expect(container.querySelector('textarea').disabled).toBe(true)
    expect(screen.getByRole('button', { name: /Stop/ })).toBeTruthy()
  })

  it('enables the composer and hides Stop when there is no active run', () => {
    const { container } = renderWith(null)
    expect(container.querySelector('textarea').disabled).toBe(false)
    expect(screen.queryByRole('button', { name: /Stop/ })).toBeNull()
  })

  it('does not block for a terminal active_run', () => {
    const { container } = renderWith({ status: 'completed' })
    expect(container.querySelector('textarea').disabled).toBe(false)
    expect(screen.queryByRole('button', { name: /Stop/ })).toBeNull()
  })
})

describe('ChatArea — Stop gating on runReady', () => {
  // Regression for codex iter 9 P2: while streaming but before run_started has
  // delivered the run id (runReady false), Stop must be hidden so the UI can't
  // issue an unguarded cancel. Once runReady is true, Stop appears.
  function renderStreaming(runReady) {
    return render(
      <ChatArea
        conversation={{ id: 'conv-1', main_service: 'vllm-test', main_system_prompt: '', mcp_servers: [], active_run: null }}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
        streaming={true}
        runReady={runReady}
        onStopStreaming={() => {}}
      />
    )
  }

  it('hides Stop while streaming until the run id is known', () => {
    renderStreaming(false)
    expect(screen.queryByRole('button', { name: /Stop/ })).toBeNull()
  })

  it('shows Stop once runReady is true', () => {
    renderStreaming(true)
    expect(screen.getByRole('button', { name: /Stop/ })).toBeTruthy()
  })
})
