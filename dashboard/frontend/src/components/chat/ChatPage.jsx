import { useEffect, useCallback, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ChatSidebar from './ChatSidebar'
import ChatArea from './ChatArea'
import useConversations from '../../hooks/useConversations'
import useProjects from '../../hooks/useProjects'
import useChat from '../../hooks/useChat'
import { updateConversation } from '../../services/chat'
import useRunningServices from '../../hooks/useRunningServices'
import useOpenRouterModels from '../../hooks/useOpenRouterModels'
import { serviceNameForModel, formatModelLabel } from '../../utils/openrouter'
import { pendingFlushDecision } from './pendingFlush'

export default function ChatPage() {
  const { conversationId } = useParams()
  const convId = conversationId || null
  const navigate = useNavigate()

  const { conversations, refresh, create, remove, removeMany, rename, patchConversation } = useConversations()
  const { projects, refresh: refreshProjects, create: createProject, rename: renameProject, remove: removeProject } = useProjects()
  const { services: runningServices } = useRunningServices()
  const { data: openRouterData } = useOpenRouterModels()
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
    runReady,
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

  // Refresh the list when a run starts (runReady) so the sidebar's active-run
  // indicator appears for the active conversation, not only after it finishes.
  useEffect(() => {
    if (runReady) {
      refresh()
    }
  }, [runReady]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleRename = useCallback(async (id, title) => {
    await rename(id, title)
    patchConversation(id, { title })
  }, [rename, patchConversation])

  // Default main model for new conversations: the first running local
  // service wins; with none running, fall back to the first curated
  // OpenRouter model (only offered when OPENROUTER_API_KEY is configured).
  // The backend requires a non-empty main_service so we can't create
  // without one.
  const openRouterModels = openRouterData?.configured ? openRouterData.current : []
  const defaultModelName =
    runningServices[0]?.name ||
    (openRouterModels[0] ? serviceNameForModel(openRouterModels[0].id) : null)

  const handleCreate = useCallback(async () => {
    if (!defaultModelName) {
      window.alert('No model available. Start a local model or configure OpenRouter.')
      return
    }
    const conv = await create({
      main_service: defaultModelName,
    })
    navigate(`/chat/${conv.id}`)
  }, [create, navigate, defaultModelName])

  const handleCreateInProject = useCallback(async (projectId) => {
    if (!defaultModelName) {
      window.alert('No model available. Start a local model or configure OpenRouter.')
      return
    }
    const conv = await create({
      main_service: defaultModelName,
      project_id: projectId,
    })
    await refreshProjects()
    navigate(`/chat/${conv.id}`)
  }, [create, navigate, defaultModelName, refreshProjects])

  const handleCreateProject = useCallback(async () => {
    const name = window.prompt('Project name')
    if (!name || !name.trim()) return
    await createProject({ name: name.trim() })
  }, [createProject])

  const handleDeleteProject = useCallback(async (id) => {
    // Conversations are detached server-side, not deleted — refresh the
    // list so they reappear as unfiled.
    await removeProject(id)
    await refresh()
  }, [removeProject, refresh])

  const handleMoveMany = useCallback(async (ids, projectId) => {
    await Promise.all(ids.map(id => updateConversation(id, { project_id: projectId })))
    await Promise.all([refresh(), refreshProjects()])
  }, [refresh, refreshProjects])

  // Empty-state composer: create a conversation, then queue the typed
  // message so it sends as soon as the new conversation loads.
  const handleCreateAndSend = useCallback(async (content, images) => {
    if (!defaultModelName) {
      window.alert('No model available. Start a local model or configure OpenRouter.')
      return
    }
    const conv = await create({ main_service: defaultModelName })
    pendingMsgRef.current = { convId: conv.id, content, images }
    navigate(`/chat/${conv.id}`)
  }, [create, navigate, defaultModelName])

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
        onRename={handleRename}
        projects={projects}
        onCreateProject={handleCreateProject}
        onRenameProject={renameProject}
        onDeleteProject={handleDeleteProject}
        onCreateInProject={handleCreateInProject}
        onMoveMany={handleMoveMany}
      />
      <ChatArea
        conversation={conversation}
        awaitingConversation={!!convId && (!conversation || conversation.id !== convId)}
        defaultModelName={formatModelLabel(defaultModelName, openRouterModels)}
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
        runReady={runReady}
        onSend={sendMessage}
        onEdit={editMessage}
        onStopStreaming={stopStreaming}
        onReloadConversation={loadConversation}
        onRefreshConversations={refresh}
      />
    </div>
  )
}
