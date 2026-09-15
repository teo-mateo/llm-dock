import { useCallback, useRef, useState } from 'react'
import { streamChat } from '../services/sse'

/**
 * Ghost chat: an ephemeral conversation that lives only in this hook's
 * state — nothing is persisted server-side (the reply stream carries no
 * message_saved / conversation_updated) and nothing is written to
 * localStorage. Closing the tab erases it.
 *
 * The message history is sent in full on every request (the endpoint is
 * stateless), so the tool-call rounds of earlier turns are reconstructed
 * from this state — the server never sees a stored row.
 */
export default function useGhostChat() {
  const [messages, setMessages] = useState([])
  const [streaming, setStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingReasoning, setStreamingReasoning] = useState('')
  const [toolEvents, setToolEvents] = useState([])
  const [streamingArtifacts, setStreamingArtifacts] = useState([])
  const [error, setError] = useState(null)

  const abortRef = useRef(null)
  const idRef = useRef(0)

  const nextId = () => `ghost-${++idRef.current}`

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const sendMessage = useCallback(async (content, images, { serviceName, mcpServers = [] } = {}) => {
    if (!content && !(images && images.length)) return
    setError(null)

    const userMessage = {
      id: nextId(),
      role: 'user',
      content: content || '',
      images: images || [],
      tool_calls: null,
      reasoning_content: null,
    }
    setMessages(prev => [...prev, userMessage])
    setStreaming(true)
    setStreamingContent('')
    setStreamingReasoning('')
    setToolEvents([])
    setStreamingArtifacts([])

    // The in-flight turn, accumulated in closure locals: content resets per
    // tool round (the display shows one round at a time), reasoning grows
    // across all of them.
    let roundContent = ''
    let turnReasoning = ''
    let turnToolCalls = []

    const controller = new AbortController()
    abortRef.current = controller

    try {
      await streamChat(
        '/chat/ghost',
        {
          service_name: serviceName,
          messages: toApiMessages([...messages, userMessage]),
          mcp_servers: mcpServers,
        },
        {
          signal: controller.signal,
          cache: 'no-store',
          onDelta: ({ content: c, reasoning_content: r }) => {
            if (c) {
              roundContent += c
              setStreamingContent(prev => prev + c)
            }
            if (r) {
              turnReasoning += r
              setStreamingReasoning(prev => prev + r)
            }
          },
          onToolCall: (evt) => {
            turnToolCalls.push({ type: 'call', ...evt })
            setToolEvents(prev => [...prev, { type: 'call', ...evt }])
          },
          onToolResult: (evt) => {
            const target = [...turnToolCalls].reverse().find(e => e.name === evt.name && !('result' in e))
            if (target) target.result = evt.result
            setToolEvents(prev => {
              const idx = [...prev].reverse().findIndex(e => e.name === evt.name && !('result' in e))
              if (idx === -1) return prev
              const i = prev.length - 1 - idx
              const next = [...prev]
              next[i] = { ...next[i], result: evt.result, server_id: evt.server_id }
              return next
            })
            // A new round begins after a tool result — the visible content is
            // the next round's, not a concatenation of all of them.
            roundContent = ''
            setStreamingContent('')
          },
          onArtifact: (evt) => setStreamingArtifacts(prev => [...prev, evt]),
          onDone: () => {
            setMessages(prev => [...prev, {
              id: nextId(),
              role: 'assistant',
              content: roundContent,
              reasoning_content: turnReasoning || null,
              images: [],
              tool_calls: turnToolCalls.length ? turnToolCalls : null,
            }])
          },
          onError: (msg) => {
            setError(msg)
          },
        },
      )
    } finally {
      setStreaming(false)
      setStreamingContent('')
      setStreamingReasoning('')
      setToolEvents([])
      setStreamingArtifacts([])
      if (abortRef.current === controller) abortRef.current = null
    }
  }, [messages])

  return {
    messages,
    streaming,
    streamingContent,
    streamingReasoning,
    toolEvents,
    streamingArtifacts,
    error,
    sendMessage,
    stopStreaming,
  }
}

/**
 * Display messages -> the OpenAI-shaped history the ghost endpoint expects.
 * Assistant tool-call rounds are rebuilt from this state: the tool loop's
 * follow-up requests need the assistant `tool_calls` + the `tool` results,
 * and the ids only have to agree WITHIN this one request, so the client
 * mints them. The namespaced `server_id__name` is reconstructed the same
 * way the server does.
 */
function toApiMessages(displayMessages) {
  const out = []
  for (const m of displayMessages) {
    if (m.role === 'user') {
      if (m.images?.length) {
        const parts = []
        if (m.content) parts.push({ type: 'text', text: m.content })
        for (const url of m.images) parts.push({ type: 'image_url', image_url: { url } })
        out.push({ role: 'user', content: parts })
      } else {
        out.push({ role: 'user', content: m.content })
      }
      continue
    }
    if (m.tool_calls?.length) {
      const calls = m.tool_calls.map((tc, i) => ({
        id: `ghost_${m.id}_${i}`,
        type: 'function',
        function: {
          name: tc.server_id ? `${tc.server_id}__${tc.name}` : tc.name,
          arguments: JSON.stringify(tc.arguments ?? {}),
        },
      }))
      const assistant = { role: 'assistant', content: m.content || null, tool_calls: calls }
      if (m.reasoning_content) assistant.reasoning_content = m.reasoning_content
      out.push(assistant)
      m.tool_calls.forEach((tc, i) => {
        out.push({ role: 'tool', tool_call_id: `ghost_${m.id}_${i}`, content: tc.result ?? '' })
      })
    } else {
      const msg = { role: 'assistant', content: m.content || '' }
      if (m.reasoning_content) msg.reasoning_content = m.reasoning_content
      out.push(msg)
    }
  }
  return out
}
