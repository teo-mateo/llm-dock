import { useState, useCallback, useRef, useEffect } from 'react'
import { getConversation, cancelRun } from '../services/chat'
import { streamChat } from '../services/sse'

export default function useChat({ onConversationUpdated } = {}) {
  const [conversation, setConversation] = useState(null)
  const [messages, setMessages] = useState([])
  const [critiques, setCritiques] = useState({})
  const [streaming, setStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingReasoning, setStreamingReasoning] = useState('')
  const [toolEvents, setToolEvents] = useState([])
  const [pendingToolCalls, setPendingToolCalls] = useState([]) // {index, name}
  const [heartbeat, setHeartbeat] = useState(null) // {elapsed_s} | null
  const [artifacts, setArtifacts] = useState({}) // {messageId: [artifact]}
  const [streamingArtifacts, setStreamingArtifacts] = useState([])
  const [streamingParseWarning, setStreamingParseWarning] = useState(null) // {kind, snippet, description} | null
  const [error, setError] = useState(null)
  const abortRef = useRef(null)
  // True between message_saved and stream-end — the title-tail phase where
  // the backend is generating the auto-title and about to emit one more
  // conversation_updated event. Skip aborting in this window so the title
  // event still arrives (and the backend isn't BrokenPiped mid-generation).
  // Reset on every new send/load/stop so it can't be stuck on stale.
  const drainingRef = useRef(false)
  // All controllers whose streams have not yet ended (active + draining).
  // Tracked separately from abortRef so the unmount cleanup can abort a
  // controller that loadConversation detached from abortRef but left
  // running on purpose (post-message_saved drain phase). Entries are
  // removed in the streamChat `finally` block when the stream resolves.
  const liveControllersRef = useRef(new Set())
  // Backend run id for the in-flight stream, captured from the run_started
  // SSE frame. Lets Stop cancel the SERVER run (not just abort the SSE fetch,
  // which — since Phase 4 — leaves the run going). Reset on each send/edit.
  const runIdRef = useRef(null)
  // Set when Stop is pressed BEFORE run_started arrived — the server already
  // created the run but we don't yet know its id, so we can't target the
  // cancel and must not abort the fetch (that would drop the run_started frame
  // and orphan the background run). onRunStarted consumes this and cancels.
  const pendingStopRef = useRef(false)
  // Mirror of the latest committed `conversation` for use in async callbacks
  // (cancel finallys) whose closures would otherwise capture a stale value.
  // Used to gate the post-cancel reconciliation so it can't clobber a
  // conversation the user has since navigated to.
  const conversationRef = useRef(null)
  useEffect(() => { conversationRef.current = conversation }, [conversation])

  // Refetch the conversation from the server WITHOUT touching the active
  // SSE stream. Used by the message_saved handler so we don't cancel our
  // own pipe before the trailing conversation_updated event (auto-title)
  // arrives.
  const refetchMessages = useCallback(async (convId) => {
    try {
      const data = await getConversation(convId)
      setConversation(data)
      setMessages(data.messages || [])
      setCritiques(data.critiques || {})
      setArtifacts(data.artifacts || {})
    } catch (err) {
      setError(err.message)
    }
  }, [])

  // Cancel a backend run, then reconcile local state with SQLite. The user
  // message was persisted at run creation, but our optimistic { id: 'temp-user' }
  // row is still in `messages`; without this refetch the next send's save
  // handler — which strips every temp-user row before appending — drops the
  // stopped prompt from the transcript. The refetch is gated on still observing
  // the same conversation: the user may navigate away while the cancel POST is
  // in flight, and refetchMessages writes conversation/messages directly, so an
  // ungated late refetch could clobber the conversation they moved to.
  const cancelAndReconcile = useCallback((runId, convId) => {
    cancelRun(runId)
      .catch(() => { /* already terminal / gone — harmless */ })
      .finally(() => {
        if (conversationRef.current?.id === convId) refetchMessages(convId)
      })
  }, [refetchMessages])

  const loadConversation = useCallback(async (convId) => {
    // Abort any in-flight stream before switching, UNLESS it's draining the
    // post-message_saved title tail (see drainingRef). Aborting that tail
    // would cancel auto-title generation server-side and drop the trailing
    // conversation_updated event. The drained stream's callbacks remain
    // valid via closures and will still patch the original conversation's
    // title in the sidebar.
    if (abortRef.current) {
      if (!drainingRef.current) abortRef.current.abort()
      abortRef.current = null
    }
    drainingRef.current = false
    setStreaming(false)
    setStreamingContent('')
    setStreamingReasoning('')
    setToolEvents([])
    setPendingToolCalls([])
    setHeartbeat(null)
    setStreamingArtifacts([])
    setStreamingParseWarning(null)
    setError(null)
    await refetchMessages(convId)
  }, [refetchMessages])

  const sendMessage = useCallback(async (content, images) => {
    if (!conversation || streaming) return
    setError(null)
    setStreaming(true)
    setStreamingContent('')
    setStreamingReasoning('')
    setToolEvents([])
    setPendingToolCalls([])
    setHeartbeat(null)
    setStreamingArtifacts([])
    setStreamingParseWarning(null)

    // Optimistically add user message
    const tempUserMsg = {
      id: 'temp-user',
      role: 'user',
      content,
      images: images || [],
      seq: messages.length > 0 ? messages[messages.length - 1].seq + 1 : 1,
    }
    setMessages(prev => [...prev, tempUserMsg])

    const controller = new AbortController()
    abortRef.current = controller
    drainingRef.current = false
    runIdRef.current = null
    pendingStopRef.current = false
    liveControllersRef.current.add(controller)

    let fullContent = ''
    let fullReasoning = ''

    const body = { content }
    if (images && images.length > 0) body.images = images

    try {
      await streamChat(
      `/chat/conversations/${conversation.id}/messages`,
      body,
      {
        signal: controller.signal,
        onDelta: ({ content: c, reasoning_content: r }) => {
          setHeartbeat(null)
          if (c) {
            fullContent += c
            setStreamingContent(prev => prev + c)
          }
          if (r) {
            fullReasoning += r
            setStreamingReasoning(prev => prev + r)
          }
        },
        onHeartbeat: (evt) => {
          setHeartbeat({ elapsed_s: evt.elapsed_s })
        },
        onParseWarning: (evt) => {
          setStreamingParseWarning({
            kind: evt.kind,
            snippet: evt.snippet,
            description: evt.description,
          })
        },
        onToolCallPending: (evt) => {
          setHeartbeat(null)
          setPendingToolCalls(prev => {
            const others = prev.filter(p => p.index !== evt.index)
            return [...others, { index: evt.index, name: evt.name }]
          })
        },
        onToolCall: (evt) => {
          setHeartbeat(null)
          setPendingToolCalls([])
          // Keep streamingReasoning growing across rounds — one continuous
          // thinking trace renders above the tool calls (mirrors the saved
          // view's single Thinking block).
          setToolEvents(prev => [...prev, { type: 'call', ...evt }])
        },
        onToolResult: (evt) => {
          setHeartbeat(null)
          setToolEvents(prev => {
            // Attach result to the matching call entry (last one with this
            // name and no result yet). Falls back to appending if no match —
            // shouldn't happen in practice but keeps the UI from dropping
            // a stray result event.
            for (let i = prev.length - 1; i >= 0; i--) {
              const e = prev[i]
              if (e.type === 'call' && e.name === evt.name && !('result' in e)) {
                const next = [...prev]
                next[i] = { ...e, result: evt.result, server_id: evt.server_id }
                return next
              }
            }
            return [...prev, { type: 'call', name: evt.name, server_id: evt.server_id, result: evt.result }]
          })
          // Reset streaming content — model will start a new response
          setStreamingContent('')
          fullContent = ''
        },
        onArtifact: (evt) => {
          setStreamingArtifacts(prev => [...prev, evt])
        },
        onDone: () => {
          // Will be followed by message_saved
        },
        onConversationUpdated,
        onRunStarted: (evt) => {
          runIdRef.current = evt.run_id
          // A Stop pressed before the id arrived deferred cancellation to here:
          // we couldn't target the server run, and aborting the fetch then would
          // have killed the very frame carrying this id. Cancel + tear down now.
          if (pendingStopRef.current) {
            pendingStopRef.current = false
            runIdRef.current = null
            cancelAndReconcile(evt.run_id, conversation.id)
            if (abortRef.current) {
              abortRef.current.abort()
              abortRef.current = null
            }
            drainingRef.current = false
          }
        },
        onMessageSaved: (data) => {
          const assistantMsg = {
            id: data.message_id,
            role: 'assistant',
            content: fullContent,
            reasoning_content: fullReasoning || null,
            model_service: conversation.main_service,
            seq: data.seq,
          }
          setMessages(prev => {
            // Replace temp user msg with real one, add assistant
            const updated = prev.filter(m => m.id !== 'temp-user')
            // Re-add user with proper seq
            const userMsg = { ...tempUserMsg, id: 'user-' + (data.seq - 1), seq: data.seq - 1 }
            return [...updated, userMsg, assistantMsg]
          })
          setStreamingContent('')
          setStreamingReasoning('')
          setStreaming(false)
          setPendingToolCalls([])
          setHeartbeat(null)
          // Enter drain: keep abortRef alive so the trailing
          // conversation_updated event can arrive, but tell loadConversation
          // not to abort if the user switches conversations now.
          drainingRef.current = true
          // Refetch from DB to get the real message IDs. MUST NOT call
          // loadConversation here — it would abort the SSE pipe and we'd
          // miss the trailing conversation_updated event (auto-title).
          refetchMessages(conversation.id)
        },
        onError: (msg) => {
          setError(msg)
          setStreaming(false)
          setStreamingContent('')
          setStreamingReasoning('')
          setPendingToolCalls([])
          setHeartbeat(null)
          drainingRef.current = false
          // Remove temp message on error
          setMessages(prev => prev.filter(m => m.id !== 'temp-user'))
        },
      }
      )
    } finally {
      liveControllersRef.current.delete(controller)
    }
  }, [conversation, messages, streaming, refetchMessages, cancelAndReconcile, onConversationUpdated])

  const editMessage = useCallback(async (msgId, content) => {
    if (!conversation || streaming) return
    const msg = messages.find(m => m.id === msgId)
    if (!msg || msg.role !== 'user') return

    setError(null)
    setStreaming(true)
    setStreamingContent('')
    setStreamingReasoning('')
    setToolEvents([])
    setPendingToolCalls([])
    setHeartbeat(null)
    setStreamingArtifacts([])
    setStreamingParseWarning(null)

    // Truncate messages from this point
    setMessages(prev => {
      const truncated = prev.filter(m => m.seq < msg.seq)
      return [...truncated, { ...msg, content, id: 'temp-edit' }]
    })

    const controller = new AbortController()
    abortRef.current = controller
    drainingRef.current = false
    runIdRef.current = null
    pendingStopRef.current = false
    liveControllersRef.current.add(controller)

    let fullContent = ''
    let fullReasoning = ''

    try {
      await streamChat(
        `/chat/conversations/${conversation.id}/messages/${msgId}`,
        { content },
        {
          method: 'PUT',
          signal: controller.signal,
          onDelta: ({ content: c, reasoning_content: r }) => {
            setHeartbeat(null)
            if (c) {
              fullContent += c
              setStreamingContent(prev => prev + c)
            }
            if (r) {
              fullReasoning += r
              setStreamingReasoning(prev => prev + r)
            }
          },
          onHeartbeat: (evt) => {
            setHeartbeat({ elapsed_s: evt.elapsed_s })
          },
          onParseWarning: (evt) => {
            setStreamingParseWarning({
              kind: evt.kind,
              snippet: evt.snippet,
              description: evt.description,
            })
          },
          onToolCallPending: (evt) => {
            setHeartbeat(null)
            setPendingToolCalls(prev => {
              const others = prev.filter(p => p.index !== evt.index)
              return [...others, { index: evt.index, name: evt.name }]
            })
          },
          onToolCall: (evt) => {
            setHeartbeat(null)
            setPendingToolCalls([])
            setToolEvents(prev => [...prev, { type: 'call', ...evt }])
          },
          onToolResult: (evt) => {
            setHeartbeat(null)
            setToolEvents(prev => {
              for (let i = prev.length - 1; i >= 0; i--) {
                const e = prev[i]
                if (e.type === 'call' && e.name === evt.name && !('result' in e)) {
                  const next = [...prev]
                  next[i] = { ...e, result: evt.result, server_id: evt.server_id }
                  return next
                }
              }
              return [...prev, { type: 'call', name: evt.name, server_id: evt.server_id, result: evt.result }]
            })
            setStreamingContent('')
            fullContent = ''
          },
          onArtifact: (evt) => {
            setStreamingArtifacts(prev => [...prev, evt])
          },
          onDone: () => {},
          onConversationUpdated,
          onRunStarted: (evt) => {
            runIdRef.current = evt.run_id
            if (pendingStopRef.current) {
              pendingStopRef.current = false
              runIdRef.current = null
              cancelAndReconcile(evt.run_id, conversation.id)
              if (abortRef.current) {
                abortRef.current.abort()
                abortRef.current = null
              }
              drainingRef.current = false
            }
          },
          onMessageSaved: () => {
            setStreamingContent('')
            setStreamingReasoning('')
            setStreaming(false)
            setHeartbeat(null)
            // See note in sendMessage: refetch only, don't abort the stream,
            // and enter the drain window so loadConversation also leaves it
            // alone if the user navigates now.
            drainingRef.current = true
            refetchMessages(conversation.id)
          },
          onError: (msg) => {
            setError(msg)
            setStreaming(false)
            setStreamingContent('')
            setStreamingReasoning('')
            setHeartbeat(null)
            setPendingToolCalls([])
            drainingRef.current = false
            loadConversation(conversation.id)
          },
        }
      )
    } finally {
      liveControllersRef.current.delete(controller)
    }
  }, [conversation, messages, streaming, loadConversation, refetchMessages, cancelAndReconcile, onConversationUpdated])

  const stopStreaming = useCallback(() => {
    // Explicit Stop must cancel the SERVER run, not just abort the SSE fetch:
    // since Phase 4 the run continues in the background after the fetch closes.
    // Navigation (loadConversation / unmount) deliberately does NOT call this —
    // it only detaches the observer, leaving the run to finish and persist.
    const runId = runIdRef.current
    const convId = conversation?.id
    if (runId) {
      // Id known: cancel the server run now (and reconcile after it settles),
      // then abort our observer.
      runIdRef.current = null
      cancelAndReconcile(runId, convId)
      if (abortRef.current) {
        abortRef.current.abort()
        abortRef.current = null
      }
    } else if (abortRef.current) {
      // Stop pressed before run_started: the server already created the run but
      // we don't know its id yet. Aborting now would drop the run_started frame
      // and leave the background run executing. Defer the abort + cancel to
      // onRunStarted, which consumes this flag the moment the id arrives.
      pendingStopRef.current = true
    }
    drainingRef.current = false
    setStreaming(false)
    setHeartbeat(null)
    setPendingToolCalls([])
  }, [conversation, cancelAndReconcile])

  // Abort streaming on unmount (e.g. navigating away). Aborts BOTH the
  // active stream (abortRef) and any detached draining streams whose
  // controllers loadConversation cleared from abortRef but left running so
  // the auto-title event could land. Without the liveControllersRef sweep,
  // those fetches would outlive the component and keep firing callbacks
  // against an unmounted React tree.
  useEffect(() => {
    return () => {
      for (const c of liveControllersRef.current) c.abort()
      liveControllersRef.current.clear()
      abortRef.current = null
    }
  }, [])

  return {
    conversation,
    messages,
    critiques,
    setCritiques,
    streaming,
    streamingContent,
    streamingReasoning,
    toolEvents,
    pendingToolCalls,
    heartbeat,
    artifacts,
    streamingArtifacts,
    streamingParseWarning,
    error,
    loadConversation,
    sendMessage,
    editMessage,
    stopStreaming,
    setConversation,
  }
}
