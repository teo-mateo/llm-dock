import { useEffect, useCallback, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ChatSidebar from './ChatSidebar'
import ChatArea from './ChatArea'
import useConversations from '../../hooks/useConversations'
import useChat from '../../hooks/useChat'
import useRunningServices from '../../hooks/useRunningServices'
import { pendingFlushDecision } from './pendingFlush'

export default function ChatPage() {
  const { conversationId } = useParams()
  const convId = conversationId || null
  const navigate = useNavigate()

  const { conversations, refresh, create, remove, removeMany, patchConversation } = useConversations()
  const { services: runningServices } = useRunningServices()
  const {
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
    cancelling,
    loadConversation,
    sendMessage,
    editMessage,
    stopStreaming,
  } = useChat({
    onConversationUpdated: (evt) => patchConversation(evt.id, { title: evt.title }),
  })

  // Holds the first message typed in the empty-state composer. The
  // conversation has to exist (and be loaded into useChat) before
  // sendMessage can fire, so we stash it here and flush it from an effect
  // once the freshly-created conversation is the active one.
  const pendingMsgRef = useRef(null)

  // Load conversation when URL changes
  useEffect(() => {
    if (convId) {
      loadConversation(convId)
    }
  }, [convId, loadConversation])

  // Flush the queued first message once its conversation is loaded.
  // loadConversation() has no request sequencing, so a late getConversation
  // for the just-created chat C can resolve and set `conversation` to C
  // even after the user has already navigated to a different chat B. Gate
  // the flush on the live route too, and abandon the queued message the
  // moment the route no longer points at it — otherwise a stale fetch
  // would fire a background send into a non-active conversation (codex
  // iteration 3, P1).
  useEffect(() => {
    const pending = pendingMsgRef.current
    const decision = pendingFlushDecision(pending, convId, conversation, streaming)
    if (decision === 'abandon') {
      pendingMsgRef.current = null
    } else if (decision === 'send') {
      pendingMsgRef.current = null
      sendMessage(pending.content, pending.images)
    }
  }, [convId, conversation, streaming, sendMessage])

  // Refresh conversation list when streaming completes (for auto-title)
  useEffect(() => {
    if (!streaming && conversation) {
      refresh()
    }
  }, [streaming]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleCreate = useCallback(async () => {
    // Default the main model to the first running service. When exactly
    // one model is up this preselects it; the backend requires a non-empty
    // main_service so we can't create without one.
    if (runningServices.length === 0) {
      window.alert('No running model services available. Start a model first.')
      return
    }
    const conv = await create({
      main_service: runningServices[0].name,
    })
    navigate(`/chat/${conv.id}`)
  }, [create, navigate, runningServices])

  // Empty-state composer: create a conversation, then queue the typed
  // message so it sends as soon as the new conversation loads.
  const handleCreateAndSend = useCallback(async (content, images) => {
    if (runningServices.length === 0) {
      window.alert('No running model services available. Start a model first.')
      return
    }
    const conv = await create({ main_service: runningServices[0].name })
    pendingMsgRef.current = { convId: conv.id, content, images }
    navigate(`/chat/${conv.id}`)
  }, [create, navigate, runningServices])

  const handleSelect = useCallback((id) => {
    navigate(`/chat/${id}`)
  }, [navigate])

  // Deletes cascade to descendant spinoffs server-side. If the active
  // conversation is one of the deleted rows OR a descendant of any of
  // them, navigate away — otherwise the URL would point at a now-404
  // conversation. Walk the parent chain client-side using the in-memory
  // conversation list (captured before the delete fires).
  const activeWillBeDeleted = useCallback((deletedIds) => {
    if (!convId) return false
    const deleted = new Set(deletedIds)
    const byId = new Map(conversations.map(c => [c.id, c]))
    let cursor = convId
    while (cursor) {
      if (deleted.has(cursor)) return true
      cursor = byId.get(cursor)?.parent_conversation_id || null
    }
    return false
  }, [convId, conversations])

  const handleDelete = useCallback(async (id) => {
    const shouldNavigate = activeWillBeDeleted([id])
    await remove(id)
    if (shouldNavigate) navigate('/chat')
  }, [remove, activeWillBeDeleted, navigate])

  const handleDeleteMany = useCallback(async (ids) => {
    if (!ids || ids.length === 0) return
    const shouldNavigate = activeWillBeDeleted(ids)
    await removeMany(ids)
    if (shouldNavigate) navigate('/chat')
  }, [removeMany, activeWillBeDeleted, navigate])

  return (
    <div className="flex-1 flex overflow-hidden">
      <ChatSidebar
        conversations={conversations}
        activeId={convId}
        onSelect={handleSelect}
        onCreate={handleCreate}
        onDelete={handleDelete}
        onDeleteMany={handleDeleteMany}
      />
      <ChatArea
        conversation={conversation}
        awaitingConversation={!!convId && (!conversation || conversation.id !== convId)}
        defaultModelName={runningServices[0]?.name || null}
        onCreateAndSend={handleCreateAndSend}
        messages={messages}
        critiques={critiques}
        setCritiques={setCritiques}
        streaming={streaming}
        streamingContent={streamingContent}
        streamingReasoning={streamingReasoning}
        toolEvents={toolEvents}
        pendingToolCalls={pendingToolCalls}
        heartbeat={heartbeat}
        artifacts={artifacts}
        streamingArtifacts={streamingArtifacts}
        streamingParseWarning={streamingParseWarning}
        error={error}
        cancelling={cancelling}
        onSend={sendMessage}
        onEdit={editMessage}
        onStopStreaming={stopStreaming}
        onReloadConversation={loadConversation}
        onRefreshConversations={refresh}
      />
    </div>
  )
}
