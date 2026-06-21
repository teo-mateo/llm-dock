import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import useChat from './useChat'

// streamChat is the SSE driver. We replace it with a controllable fake that
// leaves the stream "in-flight" via a promise the test resolves, so we can
// exercise Stop / navigate while a turn is mid-flight.
const { mockStreamChat } = vi.hoisted(() => ({ mockStreamChat: vi.fn() }))
vi.mock('../services/sse', () => ({
  streamChat: (...args) => mockStreamChat(...args),
}))

const { mockCancelActiveRun, mockGetConversation } = vi.hoisted(() => ({
  mockCancelActiveRun: vi.fn(),
  mockGetConversation: vi.fn(),
}))
vi.mock('../services/chat', () => ({
  cancelActiveRun: (...args) => mockCancelActiveRun(...args),
  getConversation: (...args) => mockGetConversation(...args),
}))

const CONV = { id: 'conv-1', main_service: 'vllm-test' }

// streamChat fake: stay open until the test resolves it. Emits a run_started
// frame (so the hook captures the run id used as the cancel guard) unless runId
// is null, which models the early-Stop window before run_started arrives.
function installInFlightStream(runId = 'run-123') {
  let resolveStream
  const streamDone = new Promise((res) => { resolveStream = res })
  mockStreamChat.mockImplementation((_url, _body, handlers) => {
    if (runId) handlers.onRunStarted?.({ type: 'run_started', run_id: runId })
    return streamDone
  })
  return { end: () => resolveStream() }
}

beforeEach(() => {
  mockStreamChat.mockReset()
  mockCancelActiveRun.mockReset()
  mockGetConversation.mockReset()
  mockCancelActiveRun.mockResolvedValue({ run: null })
  mockGetConversation.mockResolvedValue({ ...CONV, messages: [], critiques: {}, artifacts: {} })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useChat stop/cancel wiring', () => {
  it('stopStreaming cancels the conversation\'s active run by conversation id', async () => {
    installInFlightStream()
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('hello')
      await Promise.resolve()
    })

    expect(result.current.streaming).toBe(true)

    act(() => { result.current.stopStreaming() })

    expect(mockCancelActiveRun).toHaveBeenCalledTimes(1)
    // Cancel targets the conversation, guarded by the captured run id so a late
    // cancel can't kill a newer run.
    expect(mockCancelActiveRun).toHaveBeenCalledWith('conv-1', 'run-123')
    expect(result.current.streaming).toBe(false)
  })

  it('Stop cancels even when no run_started frame has been received yet', async () => {
    // The whole point of cancel-by-conversation: the server creates the run
    // when the turn starts, so Stop works without the client first capturing a
    // run id. Earlier (run-id-keyed) designs could orphan the run in this
    // window; this asserts the cancel POST always fires (with no guard, since
    // the active run is provably still the one the user meant).
    installInFlightStream(null)
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('hello')
      await Promise.resolve()
    })

    act(() => { result.current.stopStreaming() })

    expect(mockCancelActiveRun).toHaveBeenCalledWith('conv-1', null)
  })

  it('switching conversation during a run does NOT cancel the backend run', async () => {
    // Background-run semantics: navigating away leaves the run going so it
    // finishes and persists. Only an explicit Stop cancels it.
    installInFlightStream()
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('hello')
      await Promise.resolve()
    })

    await act(async () => {
      await result.current.loadConversation('conv-2')
    })

    expect(mockCancelActiveRun).not.toHaveBeenCalled()
    expect(result.current.streaming).toBe(false)
  })

  it('Stop reconciles the optimistic row so a later send keeps the stopped prompt', async () => {
    // Regression for codex iter 1 P1: the user message is persisted at run
    // creation, but the optimistic temp-user row would be stripped by the next
    // send's save handler. Stop must refetch so the stopped prompt survives
    // with a real (non-temp) id.
    installInFlightStream()
    mockGetConversation.mockResolvedValue({
      ...CONV,
      messages: [{ id: 'msg-1', role: 'user', content: 'first', seq: 1 }],
      critiques: {},
      artifacts: {},
    })
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('first')
      await Promise.resolve()
    })
    expect(result.current.messages.some(m => m.id === 'temp-user')).toBe(true)

    await act(async () => {
      result.current.stopStreaming()
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mockCancelActiveRun).toHaveBeenCalledWith('conv-1', 'run-123')
    // The stopped prompt now carries the persisted id, not 'temp-user', so the
    // next send's `filter(m => m.id !== 'temp-user')` can no longer drop it.
    expect(result.current.messages.some(m => m.id === 'temp-user')).toBe(false)
    expect(result.current.messages.some(m => m.id === 'msg-1' && m.content === 'first')).toBe(true)
  })

  it('a late Stop refetch does not clobber a conversation the user navigated to', async () => {
    // Regression for codex iter 2 P2: stopStreaming refetches after cancel
    // settles. If the user navigates A -> B while the cancel POST is in flight,
    // the A refetch must NOT overwrite B (refetchMessages writes conversation
    // /messages directly).
    installInFlightStream()
    // Hold the cancel POST open so its reconcile finally runs LAST.
    let resolveCancel
    mockCancelActiveRun.mockImplementation(() => new Promise((res) => { resolveCancel = res }))
    mockGetConversation.mockImplementation((id) =>
      Promise.resolve(
        id === 'conv-2'
          ? { id: 'conv-2', main_service: 'svc', messages: [{ id: 'b1', role: 'user', content: 'B', seq: 1 }], critiques: {}, artifacts: {} }
          : { ...CONV, messages: [{ id: 'a1', role: 'user', content: 'A', seq: 1 }], critiques: {}, artifacts: {} }
      )
    )
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('A')
      await Promise.resolve()
    })

    // Stop A (cancel POST is now pending, reconcile finally not yet run).
    act(() => { result.current.stopStreaming() })

    // Navigate to B; B loads fully.
    await act(async () => {
      await result.current.loadConversation('conv-2')
    })
    expect(result.current.conversation.id).toBe('conv-2')

    // A's cancel resolves LAST — its reconcile must be gated out.
    await act(async () => {
      resolveCancel({ run: null })
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.conversation.id).toBe('conv-2')
  })

  it('stopStreaming with no active conversation is a harmless no-op', async () => {
    const { result } = renderHook(() => useChat({}))
    // No conversation loaded.
    act(() => { result.current.stopStreaming() })
    expect(mockCancelActiveRun).not.toHaveBeenCalled()
    expect(result.current.streaming).toBe(false)
  })
})
