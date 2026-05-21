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
// The conversation-branch tests keep SystemPromptEditor and ChatInput real.
vi.mock('./ModelSelector', () => ({ default: () => null }))
vi.mock('./McpToggle', () => ({ default: () => null }))
vi.mock('./MessageList', () => ({ default: () => null }))

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

describe('ChatArea — send gating on a pending system-prompt save', () => {
  // Regression for PR #44 codex iteration 1: SystemPromptEditor persists on
  // blur; focusing the composer blurs it, so a save can be in flight when
  // the user hits send. The send must wait for that PUT or the backend
  // generates the first reply with the stale prompt.
  beforeEach(() => {
    mockUpdateConversation.mockReset()
  })

  function renderConversation(onSend) {
    return render(
      <ChatArea
        conversation={{
          id: 'conv-1',
          main_service: 'vllm-test',
          main_system_prompt: 'original',
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

  it('waits for an in-flight prompt save before sending the message', async () => {
    let resolveSave
    mockUpdateConversation.mockReturnValue(new Promise((r) => { resolveSave = r }))
    const onSend = vi.fn()
    const { container } = renderConversation(onSend)

    // Edit + blur the system prompt — starts the (still-pending) save.
    fireEvent.click(screen.getByRole('button', { name: /System Prompt/ }))
    const promptTextarea = container.querySelectorAll('textarea')[0]
    fireEvent.change(promptTextarea, { target: { value: 'edited prompt' } })
    fireEvent.blur(promptTextarea)
    expect(mockUpdateConversation).toHaveBeenCalledWith('conv-1', { main_system_prompt: 'edited prompt' })

    // Send a message before the save resolves.
    const composer = container.querySelectorAll('textarea')[1]
    fireEvent.change(composer, { target: { value: 'hello model' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    // The send must be held while the prompt PUT is in flight.
    await Promise.resolve()
    expect(onSend).not.toHaveBeenCalled()

    // Once the save lands, the send proceeds.
    resolveSave({})
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('hello model', undefined))
  })

  it('sends when there is no pending prompt save', async () => {
    const onSend = vi.fn()
    const { container } = renderConversation(onSend)
    const composer = container.querySelector('textarea') // prompt editor collapsed
    fireEvent.change(composer, { target: { value: 'hi' } })
    fireEvent.keyDown(composer, { key: 'Enter' })
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('hi', undefined))
  })

  it('still sends if the prompt save fails', async () => {
    mockUpdateConversation.mockRejectedValue(new Error('save failed'))
    const onSend = vi.fn()
    const { container } = renderConversation(onSend)

    fireEvent.click(screen.getByRole('button', { name: /System Prompt/ }))
    const promptTextarea = container.querySelectorAll('textarea')[0]
    fireEvent.change(promptTextarea, { target: { value: 'edited' } })
    fireEvent.blur(promptTextarea)

    const composer = container.querySelectorAll('textarea')[1]
    fireEvent.change(composer, { target: { value: 'hello' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('hello', undefined))
  })

  it('waits for the whole save chain when an edit lands during a save', async () => {
    // Regression for PR #44 codex iteration 3: when a second edit is made
    // while the first save is in flight, SystemPromptEditor's commit loop
    // issues a follow-up PUT after the first resolves. The send must wait
    // for that follow-up too — not just the first promise — or the reply
    // is generated with the intermediate prompt.
    let resolveA, resolveB
    mockUpdateConversation
      .mockImplementationOnce(() => new Promise((r) => { resolveA = r }))
      .mockImplementationOnce(() => new Promise((r) => { resolveB = r }))
    const onSend = vi.fn()
    const { container } = renderConversation(onSend)

    fireEvent.click(screen.getByRole('button', { name: /System Prompt/ }))
    const promptTextarea = container.querySelectorAll('textarea')[0]

    // Edit to A and blur → save A starts (deferred).
    fireEvent.change(promptTextarea, { target: { value: 'A' } })
    fireEvent.blur(promptTextarea)
    // Edit to B and blur → dropped by the editor's saving guard.
    fireEvent.change(promptTextarea, { target: { value: 'B' } })
    fireEvent.blur(promptTextarea)

    // Send while save A is still in flight.
    const composer = container.querySelectorAll('textarea')[1]
    fireEvent.change(composer, { target: { value: 'hello' } })
    fireEvent.keyDown(composer, { key: 'Enter' })
    await Promise.resolve()
    expect(onSend).not.toHaveBeenCalled()

    // A resolves → the editor enqueues save B → send must STILL be held.
    resolveA({})
    await waitFor(() => expect(mockUpdateConversation).toHaveBeenCalledTimes(2))
    expect(mockUpdateConversation).toHaveBeenNthCalledWith(2, 'conv-1', { main_system_prompt: 'B' })
    expect(onSend).not.toHaveBeenCalled()

    // Only once B lands does the send proceed.
    resolveB({})
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('hello', undefined))
  })
})
