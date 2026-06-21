import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import useChat from './useChat'

// streamChat is the SSE driver. We replace it with a controllable fake that
// captures the handlers, fires onRunStarted (so the hook learns the backend
// run id), and then leaves the stream "in-flight" via a promise we resolve
// from the test.
const { mockStreamChat } = vi.hoisted(() => ({ mockStreamChat: vi.fn() }))
vi.mock('../services/sse', () => ({
  streamChat: (...args) => mockStreamChat(...args),
}))

const { mockCancelRun, mockGetConversation } = vi.hoisted(() => ({
  mockCancelRun: vi.fn(),
  mockGetConversation: vi.fn(),
}))
vi.mock('../services/chat', () => ({
  cancelRun: (...args) => mockCancelRun(...args),
  getConversation: (...args) => mockGetConversation(...args),
}))

const CONV = { id: 'conv-1', main_service: 'vllm-test' }

// streamChat fake: synchronously emit run_started, then return a promise that
// only resolves when the test calls the stored resolver. Returns that resolver
// via the `pending` ref so the test can end the stream deterministically.
function installInFlightStream(runId = 'run-123') {
  let resolveStream
  const streamDone = new Promise((res) => { resolveStream = res })
  mockStreamChat.mockImplementation((_url, _body, handlers) => {
    handlers.onRunStarted?.({ type: 'run_started', run_id: runId })
    return streamDone
  })
  return { end: () => resolveStream() }
}

beforeEach(() => {
  mockStreamChat.mockReset()
  mockCancelRun.mockReset()
  mockGetConversation.mockReset()
  mockCancelRun.mockResolvedValue({})
  mockGetConversation.mockResolvedValue({ ...CONV, messages: [], critiques: {}, artifacts: {} })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useChat stop/cancel wiring', () => {
  it('stopStreaming cancels the backend run captured from run_started', async () => {
    installInFlightStream('run-123')
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('hello')
      await Promise.resolve()
    })

    expect(result.current.streaming).toBe(true)

    act(() => { result.current.stopStreaming() })

    expect(mockCancelRun).toHaveBeenCalledTimes(1)
    expect(mockCancelRun).toHaveBeenCalledWith('run-123')
    expect(result.current.streaming).toBe(false)
  })

  it('switching conversation during a run does NOT cancel the backend run', async () => {
    // Background-run semantics: navigating away leaves the run going so it
    // finishes and persists. Only an explicit Stop cancels it.
    installInFlightStream('run-456')
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('hello')
      await Promise.resolve()
    })

    await act(async () => {
      await result.current.loadConversation('conv-2')
    })

    expect(mockCancelRun).not.toHaveBeenCalled()
    // The observer detaches locally (streaming flips off) but the server run
    // is untouched.
    expect(result.current.streaming).toBe(false)
  })

  it('Stop reconciles the optimistic row so a later send keeps the stopped prompt', async () => {
    // Regression for codex iter 1 P1: the user message is persisted at run
    // creation, but the optimistic temp-user row would be stripped by the next
    // send's save handler. Stop must refetch so the stopped prompt survives
    // with a real (non-temp) id.
    installInFlightStream('run-1')
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
    // Optimistic row is present and temporary at this point.
    expect(result.current.messages.some(m => m.id === 'temp-user')).toBe(true)

    await act(async () => {
      result.current.stopStreaming()
      // Let cancelRun resolve and the trailing refetch settle.
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mockCancelRun).toHaveBeenCalledWith('run-1')
    // The stopped prompt now carries the persisted id, not 'temp-user', so the
    // next send's `filter(m => m.id !== 'temp-user')` can no longer drop it.
    expect(result.current.messages.some(m => m.id === 'temp-user')).toBe(false)
    expect(result.current.messages.some(m => m.id === 'msg-1' && m.content === 'first')).toBe(true)
  })

  it('Stop pressed before run_started defers cancellation until the run id arrives', async () => {
    // Regression for codex iter 2 P2: the server creates the run before
    // emitting run_started. A Stop in that window has no id to target; aborting
    // the fetch then would drop the run_started frame and orphan the background
    // run. Stop must defer and cancel once the id lands.
    let handlers
    mockStreamChat.mockImplementation((_url, _body, h) => {
      handlers = h
      // No run_started yet; stream stays open.
      return new Promise(() => {})
    })
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('hello')
      await Promise.resolve()
    })

    // Stop before the id is known: UI reflects stopped immediately, but we
    // can't cancel the server run yet.
    act(() => { result.current.stopStreaming() })
    expect(mockCancelRun).not.toHaveBeenCalled()
    expect(result.current.streaming).toBe(false)

    // The id finally arrives — deferred cancel fires now.
    await act(async () => {
      handlers.onRunStarted({ type: 'run_started', run_id: 'run-late' })
      await Promise.resolve()
    })
    expect(mockCancelRun).toHaveBeenCalledWith('run-late')
  })

  it('a late Stop refetch does not clobber a conversation the user navigated to', async () => {
    // Regression for codex iter 2 P2: stopStreaming refetches after cancel
    // settles. If the user navigates A -> B while the cancel POST is in flight,
    // the A refetch must NOT overwrite B (refetchMessages writes conversation
    // /messages directly).
    installInFlightStream('run-A')
    // Hold the cancel POST open so its reconcile finally runs LAST.
    let resolveCancel
    mockCancelRun.mockImplementation(() => new Promise((res) => { resolveCancel = res }))
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
      resolveCancel()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(result.current.conversation.id).toBe('conv-2')
  })

  it('stopStreaming does not cancel when run_started never arrives', async () => {
    // Stream that never emits run_started (e.g. an early HTTP error path).
    // Stop defers, but with no id ever delivered there is nothing to cancel.
    let resolveStream
    mockStreamChat.mockImplementation(() => new Promise((res) => { resolveStream = res }))
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('hello')
      await Promise.resolve()
    })

    act(() => { result.current.stopStreaming() })

    expect(mockCancelRun).not.toHaveBeenCalled()
    if (resolveStream) resolveStream()
  })
})
