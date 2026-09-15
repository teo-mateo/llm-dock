import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import useGhostChat from './useGhostChat'

const { mockStreamChat } = vi.hoisted(() => ({ mockStreamChat: vi.fn() }))
vi.mock('../services/sse', () => ({
  streamChat: (...args) => mockStreamChat(...args),
}))

// The fake stream drives the hook's handlers synchronously, in wire order,
// then resolves — mirroring how the real SSE frames arrive.
function installStream(script) {
  mockStreamChat.mockImplementation((_url, _body, handlers) => {
    for (const [kind, payload] of script) handlers[kind]?.(payload)
    return Promise.resolve()
  })
}

beforeEach(() => {
  mockStreamChat.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useGhostChat', () => {
  it('sends the full history with the service name, mcp servers, and no-store cache', async () => {
    installStream([['onDelta', { content: 'hi', reasoning_content: null }], ['onDone', {}]])
    const { result } = renderHook(() => useGhostChat())

    await act(async () => {
      await result.current.sendMessage('hello', [], { serviceName: 'vllm-a', mcpServers: ['sympy-math'] })
    })

    expect(mockStreamChat).toHaveBeenCalledTimes(1)
    const [url, body, opts] = mockStreamChat.mock.calls[0]
    expect(url).toBe('/chat/ghost')
    expect(body.service_name).toBe('vllm-a')
    expect(body.mcp_servers).toEqual(['sympy-math'])
    expect(body.messages).toEqual([{ role: 'user', content: 'hello' }])
    expect(opts.cache).toBe('no-store')
    expect(result.current.messages).toHaveLength(2)
    expect(result.current.messages[1]).toMatchObject({ role: 'assistant', content: 'hi' })
  })

  it('accumulates deltas and reasoning, finalizing them into the assistant message', async () => {
    let resolveStream
    let handlers
    const streamDone = new Promise((res) => { resolveStream = res })
    mockStreamChat.mockImplementation((_url, _body, h) => {
      handlers = h
      h.onDelta?.({ content: 'a', reasoning_content: 'think-1' })
      h.onDelta?.({ content: 'b', reasoning_content: null })
      return streamDone
    })
    const { result } = renderHook(() => useGhostChat())

    await act(async () => {
      result.current.sendMessage('q', [], { serviceName: 'vllm-a' })
    })

    expect(result.current.streaming).toBe(true)
    expect(result.current.streamingContent).toBe('ab')
    expect(result.current.streamingReasoning).toBe('think-1')

    await act(async () => {
      handlers.onDone?.(null)
      resolveStream()
    })
    expect(result.current.streaming).toBe(false)
    expect(result.current.messages).toHaveLength(2)
    expect(result.current.messages[1]).toMatchObject({ role: 'assistant', content: 'ab', reasoning_content: 'think-1' })
    expect(result.current.streamingContent).toBe('')
  })

  it('a tool round resets the visible content and finalizes tool_calls with results', async () => {
    installStream([
      ['onDelta', { content: 'let me check', reasoning_content: null }],
      ['onToolCall', { name: 'solve', arguments: { eq: '2+2' }, server_id: 'sympy-math' }],
      ['onToolResult', { name: 'solve', result: '4', server_id: 'sympy-math' }],
      ['onDelta', { content: ' the answer is 4', reasoning_content: null }],
      ['onDone', {}],
    ])
    const { result } = renderHook(() => useGhostChat())

    await act(async () => {
      await result.current.sendMessage('what is 2+2', [], { serviceName: 'vllm-a', mcpServers: ['sympy-math'] })
    })

    const assistant = result.current.messages[1]
    expect(assistant.content).toBe(' the answer is 4')
    expect(assistant.tool_calls).toHaveLength(1)
    expect(assistant.tool_calls[0]).toMatchObject({ name: 'solve', server_id: 'sympy-math', result: '4' })
    expect(result.current.toolEvents).toEqual([])
  })

  it('reconstructs the tool round in the next request with matching ids and namespaced names', async () => {
    installStream([
      ['onToolCall', { name: 'solve', arguments: { eq: '2+2' }, server_id: 'sympy-math' }],
      ['onToolResult', { name: 'solve', result: '4', server_id: 'sympy-math' }],
      ['onDelta', { content: '4', reasoning_content: null }],
      ['onDone', {}],
    ])
    const { result } = renderHook(() => useGhostChat())

    await act(async () => {
      await result.current.sendMessage('what is 2+2', [], { serviceName: 'vllm-a', mcpServers: ['sympy-math'] })
    })

    // The follow-up turn: the history must carry the assistant tool_calls and
    // the tool result, ids agreeing within the request, names namespaced.
    installStream([['onDelta', { content: 'ok', reasoning_content: null }], ['onDone', {}]])
    await act(async () => {
      await result.current.sendMessage('and 3+3?', [], { serviceName: 'vllm-a', mcpServers: ['sympy-math'] })
    })

    const followUp = mockStreamChat.mock.calls[1][1].messages
    expect(followUp).toHaveLength(4)
    expect(followUp[0]).toEqual({ role: 'user', content: 'what is 2+2' })
    expect(followUp[1].role).toBe('assistant')
    expect(followUp[1].tool_calls[0].function.name).toBe('sympy-math__solve')
    expect(followUp[1].tool_calls[0].function.arguments).toBe('{"eq":"2+2"}')
    expect(followUp[2]).toEqual({
      role: 'tool',
      tool_call_id: followUp[1].tool_calls[0].id,
      content: '4',
    })
    expect(followUp[2].tool_call_id).toBe(`ghost_${result.current.messages[1].id}_0`)
    expect(followUp[3]).toEqual({ role: 'user', content: 'and 3+3?' })
  })

  it('sends images as multipart content parts on the wire', async () => {
    installStream([['onDelta', { content: 'ok', reasoning_content: null }], ['onDone', {}]])
    const { result } = renderHook(() => useGhostChat())

    await act(async () => {
      await result.current.sendMessage('what is this', ['data:image/png;base64,AAA'], { serviceName: 'vllm-a' })
    })

    const [url, body] = mockStreamChat.mock.calls[0]
    expect(url).toBe('/chat/ghost')
    expect(body.messages[0].content).toEqual([
      { type: 'text', text: 'what is this' },
      { type: 'image_url', image_url: { url: 'data:image/png;base64,AAA' } },
    ])
  })

  it('a stream error surfaces and no assistant message is finalized', async () => {
    installStream([['onError', 'service unreachable']])
    const { result } = renderHook(() => useGhostChat())

    await act(async () => {
      await result.current.sendMessage('hello', [], { serviceName: 'vllm-dead' })
    })

    expect(result.current.error).toBe('service unreachable')
    expect(result.current.messages).toHaveLength(1) // user message only
    expect(result.current.streaming).toBe(false)
  })

  it('stopStreaming aborts the in-flight stream', async () => {
    const mockAbort = vi.fn()
    const abortSignal = { aborted: false, addEventListener: vi.fn() }
    let resolveStream
    const streamDone = new Promise((res) => { resolveStream = res })
    class FakeController {
      constructor() {
        this.signal = abortSignal
        this.abort = mockAbort
      }
    }
    const realController = globalThis.AbortController
    vi.spyOn(globalThis, 'AbortController').mockImplementation(FakeController)
    mockStreamChat.mockImplementation((_url, _body, handlers) => {
      handlers.onDelta?.({ content: 'a', reasoning_content: null })
      return streamDone
    })
    const { result } = renderHook(() => useGhostChat())

    await act(async () => {
      result.current.sendMessage('hello', [], { serviceName: 'vllm-a' })
    })

    expect(mockStreamChat.mock.calls[0][2].signal).toBe(abortSignal)
    act(() => { result.current.stopStreaming() })
    expect(mockAbort).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveStream()
    })
    // An aborted turn finalizes nothing — the partial stays out of the
    // history, same as a cancelled persisted run.
    expect(result.current.messages).toHaveLength(1)
    vi.restoreAllMocks()
    globalThis.AbortController = realController
  })

  it('artifacts from tool results accumulate into streamingArtifacts while in flight', async () => {
    let resolveStream
    const streamDone = new Promise((res) => { resolveStream = res })
    mockStreamChat.mockImplementation((_url, _body, handlers) => {
      handlers.onArtifact?.({ artifact_type: 'html', title: 'Rendered', content: '<b>x</b>' })
      handlers.onDelta?.({ content: 'working', reasoning_content: null })
      return streamDone
    })
    const { result } = renderHook(() => useGhostChat())

    await act(async () => {
      result.current.sendMessage('render it', [], { serviceName: 'vllm-a' })
    })

    expect(result.current.streaming).toBe(true)
    expect(result.current.streamingArtifacts).toEqual([
      { artifact_type: 'html', title: 'Rendered', content: '<b>x</b>' },
    ])
    expect(result.current.streamingContent).toBe('working')

    // Complete the stream: the artifacts clear with the in-flight state.
    await act(async () => { resolveStream() })
    expect(result.current.streaming).toBe(false)
    expect(result.current.streamingArtifacts).toEqual([])
  })
})
