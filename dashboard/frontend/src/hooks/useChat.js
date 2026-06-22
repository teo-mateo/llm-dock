import { useState, useCallback, useRef, useEffect } from 'react'
import { getConversation, cancelActiveRun } from '../services/chat'
import { streamChat } from '../services/sse'

// A conversation has a live background run when its active_run is queued or
// running. Used to block send/edit (and to find the run id for Stop) when we
// returned to a conversation whose run is still going but we hold no SSE stream.
function isRunActive(run) {
  return !!run && (run.status === 'running' || run.status === 'queued')
}

export default function useChat({ onConversationUpdated } = {}) {
  const [conversation, setConversation] = useState(null)
  const [messages, setMessages] = useState([])
  const [critiques, setCritiques] = useState({})
  const [streaming, setStreaming] = useState(false)
  // True once the run id for the in-flight stream is known (run_started parsed).
  // The Stop control is gated on this so it is never offered without a run id —
  // every Stop therefore sends an expected-run guard, never an unguarded cancel
  // that a concurrently-started run (another tab/client) could be hit by.
  const [runReady, setRunReady] = useState(false)
  // True from Stop until the cancel POST (and its reconcile) settle. Blocks a
  // new send/edit during that window so an unguarded cancel can't be processed
  // against a run the user started after Stop — closing the early-Stop
  // (no run id) stale-cancel race. Mirrored into cancellingRef for the
  // synchronous guard in send/edit.
  const [cancelling, setCancelling] = useState(false)
  const cancellingRef = useRef(false)
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
  // The conversation the hook currently INTENDS to show. Set synchronously at
  // the start of loadConversation (before the fetch resolves) and mirrored from
  // committed `conversation` for the setConversation paths. Used to request-
  // sequence conversation fetches: any refetch (navigation, post-message_saved,
  // post-cancel reconcile) only applies if this still names the conversation it
  // fetched, so a late-resolving fetch can't clobber a conversation the user
  // navigated to. Must be the intended id, NOT the committed one — during
  // loadConversation(B) the committed conversation is still A until B resolves.
  const observedConvIdRef = useRef(null)
  useEffect(() => { observedConvIdRef.current = conversation?.id ?? null }, [conversation])
  // Backend run id for the in-flight stream, captured from the run_started SSE
  // frame. Stop cancels by conversation id (so it works even before this lands)
  // but passes this as an expected-run guard when known, so a late cancel can't
  // kill a newer run that started after the one the user stopped. Reset at the
  // start of each send/edit/load so it never carries a stale run's id.
  const runIdRef = useRef(null)
  // Hold the caller's onConversationUpdated behind a ref and expose a STABLE
  // wrapper. Callers (ChatPage) pass a fresh inline function each render; if the
  // stream callbacks depended on it directly, sendMessage/editMessage/reattachRun
  // — and therefore loadConversation — would change identity every render, and
  // ChatPage's URL-load effect (deps on loadConversation) would re-run and
  // reload in a loop. The wrapper's identity never changes, so those callbacks
  // stay stable.
  const onConversationUpdatedRef = useRef(onConversationUpdated)
  useEffect(() => { onConversationUpdatedRef.current = onConversationUpdated }, [onConversationUpdated])
  const handleConversationUpdated = useCallback((evt) => {
    onConversationUpdatedRef.current?.(evt)
  }, [])

  // Refetch the conversation from the server WITHOUT touching the active
  // SSE stream. Used by the message_saved handler so we don't cancel our
  // own pipe before the trailing conversation_updated event (auto-title)
  // arrives.
  const refetchMessages = useCallback(async (convId) => {
    try {
      const data = await getConversation(convId)
      // Drop the result if the user navigated to a different conversation while
      // this fetch was in flight — otherwise a late resolve writes stale
      // conversation/messages over the one now intended (request-sequencing).
      if (observedConvIdRef.current !== convId) return null
      setConversation(data)
      setMessages(data.messages || [])
      setCritiques(data.critiques || {})
      setArtifacts(data.artifacts || {})
      // Surface a run that failed while we weren't observing (e.g. a background
      // run that errored after the browser disconnected). active_run is only
      // queued/running, so a failure shows up via last_run instead.
      if (data.last_run?.status === 'failed' && data.last_run.error) {
        setError(data.last_run.error)
      }
      return data
    } catch (err) {
      if (observedConvIdRef.current !== convId) return null
      setError(err.message)
      return null
    }
  }, [])

  // Cancel a conversation's active run, then reconcile local state with SQLite.
  // Cancellation is by conversation id (not run id) so Stop works even before
  // the run_started frame has delivered the id — the server creates the run
  // when the turn starts, so it is always findable from the conversation. The
  // user message was persisted at run creation, but our optimistic
  // { id: 'temp-user' } row is still in `messages`; without this refetch the
  // next send's save handler — which strips every temp-user row before
  // appending — drops the stopped prompt from the transcript. The refetch is
  // gated on still observing the same conversation: the user may navigate away
  // while the cancel POST is in flight, and refetchMessages writes
  // conversation/messages directly, so an ungated late refetch could clobber
  // the conversation they moved to.
  const cancelAndReconcile = useCallback((convId, expectedRunId) => {
    if (!convId) return
    // Hold the cancelling flag across BOTH the cancel POST and its reconcile so
    // send/edit stay blocked until the server has processed the cancel. This is
    // what makes the no-id (early Stop) path safe: a new run can't be created
    // while an unguarded cancel is in flight, so the cancel can only ever apply
    // to the run the user actually stopped.
    cancellingRef.current = true
    setCancelling(true)
    cancelActiveRun(convId, expectedRunId)
      .catch(() => { /* no active run / already terminal — harmless */ })
      .then(() => {
        // Reconcile only if still intending this conversation (the user may
        // have navigated away — even into a still-pending load — while the
        // cancel was in flight). refetchMessages re-checks at resolution too.
        if (observedConvIdRef.current === convId) return refetchMessages(convId)
      })
      .finally(() => {
        cancellingRef.current = false
        setCancelling(false)
      })
  }, [refetchMessages])

  // Reattach to a still-running background run's live stream (the user
  // navigated away and came back). Feeds the run-stream SSE frames through the
  // same handlers as a live send so the in-progress turn renders in full — the
  // backend replays the buffered history first, then the live tail. No
  // optimistic user row here: the transcript was just refetched, so the user
  // message is already persisted.
  const reattachRun = useCallback((conv) => {
    const run = conv.active_run
    if (!isRunActive(run)) return

    setError(null)
    setStreaming(true)
    setStreamingContent('')
    setStreamingReasoning('')
    setToolEvents([])
    setPendingToolCalls([])
    setHeartbeat(null)
    setStreamingArtifacts([])
    setStreamingParseWarning(null)

    const controller = new AbortController()
    abortRef.current = controller
    drainingRef.current = false
    runIdRef.current = run.id        // id known → Stop stays guarded
    setRunReady(true)
    liveControllersRef.current.add(controller)

    // Did a terminal signal (saved / run_status / error) already reconcile this
    // reattach? If the stream instead closes silently — the run was cancelled
    // elsewhere, which the bus emits no frame for — or a setup/transport error
    // rejects the promise, we still must drop `streaming` and refetch so the
    // (now terminal) active_run can't leave the composer stuck disabled.
    let terminalSeen = false
    const reconcile = () => {
      // Gate entirely on still observing this conversation: if the user
      // navigated away (which aborted this stream), do nothing — clearing
      // `streaming` here would stomp the conversation they moved to (which may
      // itself be reattaching).
      if (observedConvIdRef.current !== conv.id) return
      setStreaming(false)
      setHeartbeat(null)
      setPendingToolCalls([])
      refetchMessages(conv.id)
    }

    streamChat(`/chat/runs/${run.id}/stream`, null, {
      method: 'GET',
      signal: controller.signal,
      onDelta: ({ content: c, reasoning_content: r }) => {
        setHeartbeat(null)
        if (c) setStreamingContent(prev => prev + c)
        if (r) setStreamingReasoning(prev => prev + r)
      },
      onHeartbeat: (evt) => setHeartbeat({ elapsed_s: evt.elapsed_s }),
      onParseWarning: (evt) => setStreamingParseWarning({
        kind: evt.kind, snippet: evt.snippet, description: evt.description,
      }),
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
        // New round begins after a tool result — reset the visible content.
        setStreamingContent('')
      },
      onArtifact: (evt) => setStreamingArtifacts(prev => [...prev, evt]),
      onConversationUpdated: handleConversationUpdated,
      onMessageSaved: () => {
        terminalSeen = true
        setStreamingContent('')
        setStreamingReasoning('')
        setStreaming(false)
        setPendingToolCalls([])
        setHeartbeat(null)
        drainingRef.current = true
        refetchMessages(conv.id)
      },
      onRunStatus: () => {
        // The run was already terminal when we reattached (it finished just
        // before/as we returned) — no live frames coming. Refetch shows the
        // persisted reply, or a failed-run error via last_run.
        terminalSeen = true
        reconcile()
      },
      onError: (msg) => {
        // A live failure delivered after attach. Surface it AND refetch so the
        // now-failed active_run stops blocking the next send/edit.
        terminalSeen = true
        setError(msg)
        setStreamingContent('')
        setStreamingReasoning('')
        drainingRef.current = false
        reconcile()
      },
    })
      .catch((err) => {
        // Setup/transport failure (token/fetch/response body) before streamChat's
        // own reader loop — it rejects here rather than calling onError.
        if (err?.name !== 'AbortError') {
          terminalSeen = true
          if (observedConvIdRef.current === conv.id) setError(err?.message || 'Reattach failed')
          reconcile()
        }
      })
      .finally(() => {
        liveControllersRef.current.delete(controller)
        // Closed with no terminal signal — the run was cancelled elsewhere (the
        // bus emits no frame for run_cancelled / stream_end). Reconcile so the
        // UI doesn't stay stuck on `streaming`.
        if (!terminalSeen) reconcile()
      })
  }, [refetchMessages, handleConversationUpdated])

  const loadConversation = useCallback(async (convId) => {
    // Claim the intended conversation synchronously, before awaiting the fetch.
    // This is what makes a concurrent post-cancel reconcile for the PREVIOUS
    // conversation skip: it gates on observedConvIdRef, which now already names
    // the conversation we're navigating to even though `conversation` state
    // still holds the old one until this fetch resolves.
    observedConvIdRef.current = convId
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
    runIdRef.current = null
    setRunReady(false)
    setStreaming(false)
    setStreamingContent('')
    setStreamingReasoning('')
    setToolEvents([])
    setPendingToolCalls([])
    setHeartbeat(null)
    setStreamingArtifacts([])
    setStreamingParseWarning(null)
    setError(null)
    const data = await refetchMessages(convId)
    // If the conversation's run is still going, reattach to its live stream so
    // the in-progress turn streams in as if we never left. Gate on the intended
    // conversation so a slow load that lost the navigation race doesn't attach.
    if (data && observedConvIdRef.current === convId && isRunActive(data.active_run)) {
      reattachRun(data)
    }
  }, [refetchMessages, reattachRun])

  const sendMessage = useCallback(async (content, images) => {
    // Block a send while a run is active for this conversation (including a
    // returned-to background run, active_run set but streaming false) — mirrors
    // the composer's disabled state and the backend active-run 409 guard.
    if (!conversation || streaming || cancellingRef.current || isRunActive(conversation.active_run)) return
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
    setRunReady(false)
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
        onConversationUpdated: handleConversationUpdated,
        onRunStarted: (evt) => { runIdRef.current = evt.run_id; setRunReady(true) },
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
  }, [conversation, messages, streaming, refetchMessages, handleConversationUpdated])

  const editMessage = useCallback(async (msgId, content) => {
    // Block edits while a run is active for this conversation — including a
    // background run we returned to (active_run set, streaming false). Without
    // this the edit optimistically truncates the transcript, then the backend
    // rejects the PUT with the active-run 409.
    if (!conversation || streaming || cancellingRef.current || isRunActive(conversation.active_run)) return
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
    setRunReady(false)
    liveControllersRef.current.add(controller)

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
              setStreamingContent(prev => prev + c)
            }
            if (r) {
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
          },
          onArtifact: (evt) => {
            setStreamingArtifacts(prev => [...prev, evt])
          },
          onDone: () => {},
          onConversationUpdated: handleConversationUpdated,
          onRunStarted: (evt) => { runIdRef.current = evt.run_id; setRunReady(true) },
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
  }, [conversation, messages, streaming, loadConversation, refetchMessages, handleConversationUpdated])

  const stopStreaming = useCallback(() => {
    // Explicit Stop must cancel the SERVER run, not just abort the SSE fetch:
    // since Phase 4 the run continues in the background after the fetch closes.
    // Cancel by conversation id so this works even if run_started has not yet
    // delivered the run id — the server created the run when the turn started,
    // so it is always findable from the conversation. Pass the captured run id
    // (when known) as an expected-run guard so a late cancel can't kill a newer
    // run started after this one. Navigation (loadConversation / unmount)
    // deliberately does NOT call this — it only detaches the observer, leaving
    // the run to finish and persist.
    // Prefer the locally-captured run id; fall back to the conversation's
    // active_run id for a run we returned to (no local stream, so runIdRef is
    // null) — still passing an expected-run guard so a late cancel can't kill a
    // newer run.
    const expectedRunId = runIdRef.current || conversation?.active_run?.id || null
    cancelAndReconcile(conversation?.id, expectedRunId)
    runIdRef.current = null
    setRunReady(false)
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
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
    runReady,
    cancelling,
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
