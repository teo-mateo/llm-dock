import { useEffect, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ChatSidebar from './ChatSidebar'
import ChatArea from './ChatArea'
import useConversations from '../../hooks/useConversations'
import useChat from '../../hooks/useChat'

export default function ChatPage() {
  const { conversationId } = useParams()
  const convId = conversationId || null
  const navigate = useNavigate()

  const { conversations, loading: convsLoading, refresh, create, remove, removeMany, patchConversation } = useConversations()
  const {
    conversation,
    messages,
    critiques,
    setCritiques,
    streaming,
    streamingContent,
    streamingReasoning,
    toolEvents,
    artifacts,
    streamingArtifacts,
    error,
    loadConversation,
    sendMessage,
    editMessage,
    stopStreaming,
  } = useChat({
    onConversationUpdated: (evt) => patchConversation(evt.id, { title: evt.title }),
  })

  // Load conversation when URL changes
  useEffect(() => {
    if (convId) {
      loadConversation(convId)
    }
  }, [convId, loadConversation])

  // Refresh conversation list when streaming completes (for auto-title)
  useEffect(() => {
    if (!streaming && conversation) {
      refresh()
    }
  }, [streaming]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleCreate = useCallback(async () => {
    // Use first available running service as default
    const conv = await create({
      main_service: 'llamacpp-gemma-4-31b-it-q8',
      sidekick_service: 'llamacpp-UNSLOTH-qwen3-5-27b-q8',
    })
    navigate(`/chat/${conv.id}`)
  }, [create, navigate])

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
        messages={messages}
        critiques={critiques}
        setCritiques={setCritiques}
        streaming={streaming}
        streamingContent={streamingContent}
        streamingReasoning={streamingReasoning}
        toolEvents={toolEvents}
        artifacts={artifacts}
        streamingArtifacts={streamingArtifacts}
        error={error}
        onSend={sendMessage}
        onEdit={editMessage}
        onStopStreaming={stopStreaming}
        onReloadConversation={loadConversation}
        onRefreshConversations={refresh}
      />
    </div>
  )
}
