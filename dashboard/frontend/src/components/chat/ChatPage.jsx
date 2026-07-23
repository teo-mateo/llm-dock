import { useEffect, useCallback, useRef, useState, useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ChatArea from './ChatArea'
import ProjectPage from './ProjectPage'
import ProjectChatSplit from './ProjectChatSplit'
import SidebarSplit from './SidebarSplit'
import useConversations from '../../hooks/useConversations'
import useProjects from '../../hooks/useProjects'
import useChat from '../../hooks/useChat'
import { updateConversation } from '../../services/chat'
import useRunningServices from '../../hooks/useRunningServices'
import useOpenRouterModels from '../../hooks/useOpenRouterModels'
import { serviceNameForModel, formatModelLabel } from '../../utils/openrouter'
import { pendingFlushDecision } from './pendingFlush'

export default function ChatPage() {
  const { conversationId, projectId } = useParams()
  const convId = conversationId || null
  const navigate = useNavigate()

  // Bumped when a chat run completes — the run may have written project
  // files via the project-files tools, so the explorer strip re-reads
  // the tree.
  const [filesRefreshKey, setFilesRefreshKey] = useState(0)

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
    deleteMessage,
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

  // Refresh conversation list when streaming completes (for auto-title),
  // and re-read the project file tree — the run may have created or
  // edited files.
  useEffect(() => {
    if (!streaming && conversation) {
      refresh()
      setFilesRefreshKey(k => k + 1)
    }
  }, [streaming]) // eslint-disable-line react-hooks/exhaustive-deps

  // Refresh the list when a run starts (runReady) so the sidebar's active-run
  // indicator appears for the active conversation, not only after it finishes.
  useEffect(() => {
    if (runReady) {
      refresh()
    }
  }, [runReady]) // eslint-disable-line react-hooks/exhaustive-deps

  // Effective project of the ACTIVE conversation — drives the file-explorer
  // strip next to the chat. Spin-offs store project_id = NULL and inherit
  // membership from their root (the DB triggers enforce this and the server
  // resolves the chain the same way), so walk up through the loaded list;
  // the list is also refreshed after moves, so a moved active conversation
  // switches strips without a conversation reload. Falls back to the loaded
  // conversation's own field when the list row isn't present (fresh chat not
  // yet in the paginated list) — gated on the id matching the route so a
  // stale mid-switch `conversation` can't show the previous chat's files.
  // Unknown project ids (deleted elsewhere) drop the strip.
  const { activeRootId, effectiveProjectId } = useMemo(() => {
    if (!convId) return { activeRootId: null, effectiveProjectId: null }
    const byId = new Map(conversations.map(c => [c.id, c]))
    let row = byId.get(convId)
    if (row) {
      const seen = new Set()
      while (row.parent_conversation_id && byId.has(row.parent_conversation_id) && !seen.has(row.id)) {
        seen.add(row.id)
        row = byId.get(row.parent_conversation_id)
      }
      return { activeRootId: row.id, effectiveProjectId: row.project_id || null }
    }
    return {
      activeRootId: convId,
      effectiveProjectId:
        conversation && conversation.id === convId ? (conversation.project_id || null) : null,
    }
  }, [convId, conversations, conversation])
  const conversationProject = effectiveProjectId
    ? projects.find(p => p.id === effectiveProjectId) || null
    : null

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

  // True while the project file editor holds unsaved changes. In-app
  // navigation unmounts the editor without its own close handler, so the
  // navigation entry points below confirm before discarding. (Browser
  // close/reload is guarded by the editor's beforeunload handler.)
  //
  // The ref is NOT cleared here: some guarded actions await a mutation
  // that can fail, leaving the editor mounted with its dirty buffer — a
  // pre-cleared ref would let the next navigation discard those edits
  // without asking (codex iteration 3, P2). The editor resets the flag
  // itself when it actually unmounts or its dirty state changes.
  const editorDirtyRef = useRef(false)
  const confirmDiscardEdits = useCallback(() => {
    if (!editorDirtyRef.current) return true
    return window.confirm('Discard unsaved changes?')
  }, [])

  const handleCreate = useCallback(async () => {
    if (!defaultModelName) {
      window.alert('No model available. Start a local model or configure OpenRouter.')
      return
    }
    if (!confirmDiscardEdits()) return
    const conv = await create({
      main_service: defaultModelName,
    })
    navigate(`/chat/${conv.id}`)
  }, [create, navigate, defaultModelName, confirmDiscardEdits])

  const handleCreateInProject = useCallback(async (projectId) => {
    if (!defaultModelName) {
      window.alert('No model available. Start a local model or configure OpenRouter.')
      return
    }
    if (!confirmDiscardEdits()) return
    const conv = await create({
      main_service: defaultModelName,
      project_id: projectId,
    })
    await refreshProjects()
    navigate(`/chat/${conv.id}`)
  }, [create, navigate, defaultModelName, refreshProjects, confirmDiscardEdits])

  const handleCreateProject = useCallback(async () => {
    const name = window.prompt('Project name')
    if (!name || !name.trim()) return
    await createProject({ name: name.trim() })
  }, [createProject])

  const handleDeleteProject = useCallback(async (id) => {
    // Deleting the project backing the active conversation's explorer
    // strip — or the project page currently open (route projectId) —
    // unmounts a possibly-dirty file editor (and removes the files
    // behind it) — run the discard guard first, cancel aborts.
    if ((id === effectiveProjectId || id === projectId) && !confirmDiscardEdits()) return
    // Conversations are detached server-side, not deleted — refresh the
    // list so they reappear as unfiled.
    await removeProject(id)
    await refresh()
    // Don't leave the URL pointing at the project page we just deleted.
    if (projectId === id) navigate('/chat')
  }, [removeProject, refresh, projectId, navigate, effectiveProjectId, confirmDiscardEdits])

  const handleMoveMany = useCallback(async (ids, projectId) => {
    // Moving the active conversation's root changes its effective
    // project; the strip then swaps (or disappears) and the split's
    // reset effect closes the editor — same silent-loss path as above.
    // ids are already root-resolved by the sidebar.
    if (ids.includes(activeRootId) && !confirmDiscardEdits()) return
    await Promise.all(ids.map(id => updateConversation(id, { project_id: projectId })))
    await Promise.all([refresh(), refreshProjects()])
  }, [refresh, refreshProjects, activeRootId, confirmDiscardEdits])

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
    if (!confirmDiscardEdits()) return
    navigate(`/chat/${id}`)
  }, [navigate, confirmDiscardEdits])

  const handleOpenProject = useCallback((id) => {
    if (!confirmDiscardEdits()) return
    navigate(`/chat/project/${id}`)
  }, [navigate, confirmDiscardEdits])

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
    // Deleting the active conversation (or an ancestor whose cascade
    // includes it) unmounts a possibly-dirty file editor via the
    // navigation below — run the same discard guard as the other
    // navigation paths, and let cancel abort the deletion.
    if (shouldNavigate && !confirmDiscardEdits()) return
    await remove(id)
    // Deleted conversations may have belonged to a project — refresh the
    // cached per-project counts so a section can't claim chats it no
    // longer has.
    await refreshProjects()
    if (shouldNavigate) navigate('/chat')
  }, [remove, refreshProjects, activeWillBeDeleted, navigate, confirmDiscardEdits])

  const handleDeleteMany = useCallback(async (ids) => {
    if (!ids || ids.length === 0) return
    const shouldNavigate = activeWillBeDeleted(ids)
    if (shouldNavigate && !confirmDiscardEdits()) return
    await removeMany(ids)
    await refreshProjects()
    if (shouldNavigate) navigate('/chat')
  }, [removeMany, refreshProjects, activeWillBeDeleted, navigate, confirmDiscardEdits])

  const sidebarRef = useRef(null)

  useEffect(() => {
    const handler = (e) => {
      if (!(e.metaKey || e.ctrlKey)) return
      const active = document.activeElement
      if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) return
      if (e.key === '[') {
        e.preventDefault()
        sidebarRef.current?.adjustWidth(-20)
      } else if (e.key === ']') {
        e.preventDefault()
        sidebarRef.current?.adjustWidth(20)
      } else if (e.key === 'b') {
        e.preventDefault()
        sidebarRef.current?.toggleCollapse()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  return (
    <SidebarSplit
      ref={sidebarRef}
      conversations={conversations}
      activeId={convId}
      onSelect={handleSelect}
      onCreate={handleCreate}
      onDelete={handleDelete}
      onDeleteMany={handleDeleteMany}
      onRename={handleRename}
      projects={projects}
      activeProjectId={projectId || null}
      onOpenProject={handleOpenProject}
      onCreateProject={handleCreateProject}
      onRenameProject={renameProject}
      onDeleteProject={handleDeleteProject}
      onCreateInProject={handleCreateInProject}
      onMoveMany={handleMoveMany}
    >
      {projectId ? (
        <ProjectPage
          project={projects.find(p => p.id === projectId) || null}
          onEditorDirtyChange={(d) => { editorDirtyRef.current = d }}
        />
      ) : (
      <ProjectChatSplit
        project={conversationProject}
        conversationId={convId}
        refreshKey={filesRefreshKey}
        onEditorDirtyChange={(d) => { editorDirtyRef.current = d }}
      >
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
        onDeleteMessage={deleteMessage}
        onStopStreaming={stopStreaming}
        onReloadConversation={loadConversation}
        onRefreshConversations={refresh}
      />
      </ProjectChatSplit>
      )}
    </SidebarSplit>
  )
}
