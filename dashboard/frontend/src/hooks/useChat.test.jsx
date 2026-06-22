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
  // Default: a stream that stays open. Reattach (loadConversation onto an
  // active_run) and any send that doesn't set its own impl get a valid promise
  // to attach to instead of undefined.
  mockStreamChat.mockImplementation(() => new Promise(() => {}))
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

  it('blocks a new send until the cancel settles, closing the unguarded race', async () => {
    // Regression for codex iter 5 P2: when Stop is pressed before run_started,
    // the cancel is unguarded (no expected_run_id). A new run must not be able
    // to start while that cancel is in flight, or the server could cancel the
    // NEW run instead. The hook blocks send/edit until the cancel settles.
    installInFlightStream(null) // early Stop: no run id captured
    let resolveCancel
    mockCancelActiveRun.mockImplementation(() => new Promise((res) => { resolveCancel = res }))
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('A')
      await Promise.resolve()
    })
    const callsAfterA = mockStreamChat.mock.calls.length

    act(() => { result.current.stopStreaming() })
    expect(mockCancelActiveRun).toHaveBeenCalledWith('conv-1', null)

    // Attempt to send B while the cancel is unresolved — must be blocked.
    await act(async () => {
      result.current.sendMessage('B')
      await Promise.resolve()
    })
    expect(mockStreamChat.mock.calls.length).toBe(callsAfterA)

    // Cancel settles → the block lifts and B can start.
    await act(async () => {
      resolveCancel({ run: null })
      await Promise.resolve()
      await Promise.resolve()
    })
    await act(async () => {
      result.current.sendMessage('B')
      await Promise.resolve()
    })
    expect(mockStreamChat.mock.calls.length).toBe(callsAfterA + 1)
  })

  it('a Stop reconcile is dropped when its cancel settles during an in-flight navigation', async () => {
    // Regression for codex iter 6 P2: the reconcile gate must use the INTENDED
    // conversation (set synchronously at loadConversation), not the committed
    // one. Repro: Stop A, navigate to B while B's fetch is still pending, then
    // A's cancel settles — the reconcile for A must be gated out (we already
    // intend B), so A is never refetched and can't clobber B.
    installInFlightStream()
    let resolveCancel
    mockCancelActiveRun.mockImplementation(() => new Promise((res) => { resolveCancel = res }))
    let resolveB
    mockGetConversation.mockImplementation((id) => {
      if (id === 'conv-2') return new Promise((res) => { resolveB = res })
      return Promise.resolve({ ...CONV, messages: [{ id: 'a1', role: 'user', content: 'A', seq: 1 }], critiques: {}, artifacts: {} })
    })
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('A')
      await Promise.resolve()
    })

    // Stop A (cancel POST held open).
    act(() => { result.current.stopStreaming() })

    // Begin navigation to B; B's fetch stays pending.
    let loadPromise
    act(() => { loadPromise = result.current.loadConversation('conv-2') })

    // A's cancel settles WHILE B is still loading.
    await act(async () => {
      resolveCancel({ run: null })
      await Promise.resolve()
      await Promise.resolve()
    })
    // The reconcile for A must have been gated out — A is never refetched.
    expect(mockGetConversation).not.toHaveBeenCalledWith('conv-1')

    // B finally resolves and wins.
    await act(async () => {
      resolveB({ id: 'conv-2', main_service: 'svc', messages: [{ id: 'b1', role: 'user', content: 'B', seq: 1 }], critiques: {}, artifacts: {} })
      await loadPromise
    })
    expect(result.current.conversation.id).toBe('conv-2')
  })

  it('Stop on a returned-to background run uses active_run.id as the cancel guard', async () => {
    // Regression for codex iter 8 P2: after navigating back there is no local
    // stream (runIdRef is null), but the loaded conversation carries active_run.
    // Stop must still send an expected-run guard so a late cancel can't kill a
    // newer run.
    const { result } = renderHook(() => useChat({}))

    act(() => {
      result.current.setConversation({ ...CONV, active_run: { id: 'run-bg', status: 'running' } })
    })

    act(() => { result.current.stopStreaming() })

    expect(mockCancelActiveRun).toHaveBeenCalledWith('conv-1', 'run-bg')
  })

  it('editMessage is blocked while the conversation has an active background run', async () => {
    // Regression for codex iter 8 P3: editing during a reattached active run
    // must not optimistically truncate the transcript only to hit the 409.
    mockGetConversation.mockResolvedValue({
      ...CONV,
      active_run: { id: 'run-bg', status: 'running' },
      messages: [{ id: 'u1', role: 'user', content: 'hi', seq: 1 }],
      critiques: {},
      artifacts: {},
    })
    const { result } = renderHook(() => useChat({}))

    await act(async () => { await result.current.loadConversation('conv-1') })
    // Loading an active-run conversation reattaches to its stream (one call);
    // the blocked edit must not open ANOTHER stream.
    const callsAfterLoad = mockStreamChat.mock.calls.length
    await act(async () => { await result.current.editMessage('u1', 'edited') })

    expect(mockStreamChat.mock.calls.length).toBe(callsAfterLoad)
    expect(result.current.messages.some(m => m.id === 'temp-edit')).toBe(false)
  })

  it('runReady stays false until run_started, gating an unguarded Stop', async () => {
    // Regression for codex iter 9 P2: the Stop control must not be exposed
    // before the run id is known, so the UI can never issue an unguarded
    // cancel. runReady is the gate; it flips true only on run_started.
    let handlers
    mockStreamChat.mockImplementation((_url, _body, h) => {
      handlers = h
      return new Promise(() => {}) // no run_started yet
    })
    const { result } = renderHook(() => useChat({}))

    act(() => { result.current.setConversation(CONV) })

    await act(async () => {
      result.current.sendMessage('hi')
      await Promise.resolve()
    })
    expect(result.current.streaming).toBe(true)
    expect(result.current.runReady).toBe(false)

    await act(async () => {
      handlers.onRunStarted({ type: 'run_started', run_id: 'run-x' })
      await Promise.resolve()
    })
    expect(result.current.runReady).toBe(true)
  })

  it('surfaces a failed background run error on load via last_run', async () => {
    // Phase 7: a run that failed while we weren't observing shows up as
    // last_run (active_run is only queued/running). loadConversation must
    // surface its error in the chat area.
    mockGetConversation.mockResolvedValue({
      ...CONV,
      active_run: null,
      last_run: { id: 'r1', status: 'failed', error: 'model exploded' },
      messages: [],
      critiques: {},
      artifacts: {},
    })
    const { result } = renderHook(() => useChat({}))

    await act(async () => { await result.current.loadConversation('conv-1') })

    expect(result.current.error).toBe('model exploded')
  })

  it('does not surface an error when the last run completed', async () => {
    mockGetConversation.mockResolvedValue({
      ...CONV,
      last_run: { id: 'r1', status: 'completed', error: null },
      messages: [],
      critiques: {},
      artifacts: {},
    })
    const { result } = renderHook(() => useChat({}))

    await act(async () => { await result.current.loadConversation('conv-1') })

    expect(result.current.error).toBeNull()
  })

  it('reattaches to the live run stream when loading an in-progress conversation', async () => {
    // The fix for the "no progress on return" bug: loading a conversation whose
    // run is still active opens GET /chat/runs/<id>/stream and renders live.
    mockGetConversation.mockResolvedValue({
      ...CONV,
      active_run: { id: 'run-bg', status: 'running' },
      messages: [{ id: 'u1', role: 'user', content: 'hi', seq: 1 }],
      critiques: {},
      artifacts: {},
    })
    let handlers
    mockStreamChat.mockImplementation((url, _body, h) => {
      handlers = { url, ...h }
      return new Promise(() => {})
    })
    const { result } = renderHook(() => useChat({}))

    await act(async () => { await result.current.loadConversation('conv-1') })

    // Opened the run-stream endpoint (GET, no body) and entered streaming.
    expect(handlers.url).toBe('/chat/runs/run-bg/stream')
    expect(handlers.method).toBe('GET')
    expect(result.current.streaming).toBe(true)
    expect(result.current.runReady).toBe(true)

    // Replayed + live deltas render into streamingContent.
    act(() => {
      handlers.onDelta({ content: 'Hello ', reasoning_content: '' })
      handlers.onDelta({ content: 'world', reasoning_content: '' })
    })
    expect(result.current.streamingContent).toBe('Hello world')
  })

  it('opens only one run stream when the same conversation is loaded twice concurrently', async () => {
    // Regression for codex iter 4 P1: React StrictMode runs the URL-load effect
    // twice on mount, and A→B→A navigation re-loads A while the first A fetch is
    // pending. Both same-id loads pass the conversation-id guard; without a load
    // generation each would open its own GET run stream and replay/live-render
    // every delta twice. Two deferred same-id loads must open exactly one stream.
    const resolvers = []
    mockGetConversation.mockImplementation(() => new Promise((res) => { resolvers.push(res) }))
    const streamUrls = []
    mockStreamChat.mockImplementation((url) => { streamUrls.push(url); return new Promise(() => {}) })
    const { result } = renderHook(() => useChat({}))

    await act(async () => {
      // Kick off both loads before either fetch resolves (StrictMode double-mount).
      const p1 = result.current.loadConversation('conv-1')
      const p2 = result.current.loadConversation('conv-1')
      const data = {
        ...CONV,
        active_run: { id: 'run-bg', status: 'running' },
        messages: [{ id: 'u1', role: 'user', content: 'hi', seq: 1 }],
        critiques: {},
        artifacts: {},
      }
      resolvers.forEach((r) => r(data))  // resolve BOTH pending fetches
      await Promise.all([p1, p2])
    })

    // Exactly one reattach stream — the superseded load did not open a second.
    expect(streamUrls).toEqual(['/chat/runs/run-bg/stream'])
    expect(result.current.streaming).toBe(true)
  })

  it('does not reattach when the loaded conversation has no active run', async () => {
    mockGetConversation.mockResolvedValue({
      ...CONV, active_run: null, messages: [], critiques: {}, artifacts: {},
    })
    const calls = []
    mockStreamChat.mockImplementation((url) => { calls.push(url); return new Promise(() => {}) })
    const { result } = renderHook(() => useChat({}))

    await act(async () => { await result.current.loadConversation('conv-1') })

    expect(calls).toEqual([])
    expect(result.current.streaming).toBe(false)
  })

  it('reattach to an already-finished run refetches instead of hanging', async () => {
    mockGetConversation.mockResolvedValue({
      ...CONV,
      active_run: { id: 'run-bg', status: 'running' },
      messages: [{ id: 'u1', role: 'user', content: 'hi', seq: 1 }],
      critiques: {},
      artifacts: {},
    })
    let handlers
    mockStreamChat.mockImplementation((url, _body, h) => { handlers = h; return new Promise(() => {}) })
    const { result } = renderHook(() => useChat({}))

    await act(async () => { await result.current.loadConversation('conv-1') })
    expect(result.current.streaming).toBe(true)

    // The run finished just as we reattached: a terminal run_status arrives.
    await act(async () => {
      handlers.onRunStatus({ type: 'run_status', status: 'completed' })
      await Promise.resolve()
    })
    expect(result.current.streaming).toBe(false)
  })

  it('reattach reconciles when the run is cancelled elsewhere (silent stream close)', async () => {
    // Codex iter 1 P1: a cancel from another tab emits no frame, so the reattach
    // stream just closes. The hook must still drop streaming + refetch.
    mockGetConversation
      .mockResolvedValueOnce({ ...CONV, active_run: { id: 'run-bg', status: 'running' }, messages: [{ id: 'u1', role: 'user', content: 'hi', seq: 1 }], critiques: {}, artifacts: {} })
      .mockResolvedValue({ ...CONV, active_run: null, messages: [{ id: 'u1', role: 'user', content: 'hi', seq: 1 }], critiques: {}, artifacts: {} })
    let resolveStream
    mockStreamChat.mockImplementation(() => new Promise((res) => { resolveStream = res }))
    const { result } = renderHook(() => useChat({}))

    await act(async () => { await result.current.loadConversation('conv-1') })
    expect(result.current.streaming).toBe(true)

    await act(async () => { resolveStream(); await Promise.resolve(); await Promise.resolve() })
    expect(result.current.streaming).toBe(false)
  })

  it('reattach reconciles on a live failure delivered after attach', async () => {
    // Codex iter 1 P1: a failure encoded as an error frame must clear the stale
    // active_run (refetch) so it stops blocking the next send.
    mockGetConversation
      .mockResolvedValueOnce({ ...CONV, active_run: { id: 'run-bg', status: 'running' }, messages: [{ id: 'u1', role: 'user', content: 'hi', seq: 1 }], critiques: {}, artifacts: {} })
      .mockResolvedValue({ ...CONV, active_run: null, last_run: { id: 'run-bg', status: 'failed', error: 'boom' }, messages: [{ id: 'u1', role: 'user', content: 'hi', seq: 1 }], critiques: {}, artifacts: {} })
    let handlers
    mockStreamChat.mockImplementation((_u, _b, h) => { handlers = h; return new Promise(() => {}) })
    const { result } = renderHook(() => useChat({}))

    await act(async () => { await result.current.loadConversation('conv-1') })
    await act(async () => { handlers.onError('boom'); await Promise.resolve(); await Promise.resolve() })

    expect(result.current.streaming).toBe(false)
    expect(result.current.error).toBeTruthy()
  })

  it('reattach reconciles when the run-stream request fails to open', async () => {
    // Codex iter 1 P2: a setup/transport failure rejects the streamChat promise
    // before its reader loop; it must not leave the UI streaming forever.
    mockGetConversation
      .mockResolvedValueOnce({ ...CONV, active_run: { id: 'run-bg', status: 'running' }, messages: [{ id: 'u1', role: 'user', content: 'hi', seq: 1 }], critiques: {}, artifacts: {} })
      .mockResolvedValue({ ...CONV, active_run: null, messages: [{ id: 'u1', role: 'user', content: 'hi', seq: 1 }], critiques: {}, artifacts: {} })
    mockStreamChat.mockImplementation(() => Promise.reject(new Error('network down')))
    const { result } = renderHook(() => useChat({}))

    await act(async () => {
      await result.current.loadConversation('conv-1')
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(result.current.streaming).toBe(false)
    expect(result.current.error).toBe('network down')
  })

  it('loadConversation stays stable when onConversationUpdated identity changes', () => {
    // Regression for codex iter 3 P1: ChatPage passes a fresh onConversationUpdated
    // every render. If loadConversation changed identity with it, ChatPage's
    // URL-load effect would re-run and reload in a loop. The hook holds the
    // callback behind a ref so loadConversation (and send/edit/reattach) stay
    // referentially stable.
    const { result, rerender } = renderHook(
      ({ cb }) => useChat({ onConversationUpdated: cb }),
      { initialProps: { cb: () => {} } },
    )
    const firstLoad = result.current.loadConversation
    const firstSend = result.current.sendMessage

    rerender({ cb: () => {} }) // brand-new callback identity

    expect(result.current.loadConversation).toBe(firstLoad)
    expect(result.current.sendMessage).toBe(firstSend)
  })

  it('stopStreaming with no active conversation is a harmless no-op', async () => {
    const { result } = renderHook(() => useChat({}))
    // No conversation loaded.
    act(() => { result.current.stopStreaming() })
    expect(mockCancelActiveRun).not.toHaveBeenCalled()
    expect(result.current.streaming).toBe(false)
  })
})
