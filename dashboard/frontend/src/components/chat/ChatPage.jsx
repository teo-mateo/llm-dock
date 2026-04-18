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

  const { conversations, loading: convsLoading, refresh, create, remove } = useConversations()
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
  } = useChat()

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

  const handleDelete = useCallback(async (id) => {
    await remove(id)
    if (convId === id) {
      navigate('/chat')
    }
  }, [remove, convId, navigate])

  return (
    <div className="flex-1 flex overflow-hidden">
      <ChatSidebar
        conversations={conversations}
        activeId={convId}
        onSelect={handleSelect}
        onCreate={handleCreate}
        onDelete={handleDelete}
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
