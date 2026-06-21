import { useState, useCallback, useRef } from 'react'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import ModelSelector from './ModelSelector'
import SystemPromptEditor from './SystemPromptEditor'
import CritiquePanel from './CritiquePanel'
import SpinoffWindow from './SpinoffWindow'
import SpinoffTaskbar from './SpinoffTaskbar'
import TextContextMenu from './TextContextMenu'
import McpToggle from './McpToggle'
import useCritique from '../../hooks/useCritique'
import { updateConversation } from '../../services/chat'

let spinoffCounter = 0

export default function ChatArea({
  conversation,
  awaitingConversation,
  defaultModelName,
  onCreateAndSend,
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
  onSend,
  onEdit,
  onStopStreaming,
  onReloadConversation,
  onRefreshConversations,
}) {
  const { critique, loading: critiqueLoading } = useCritique(setCritiques)
  const [critiqueTarget, setCritiqueTarget] = useState(null)
  const [pendingInserts, setPendingInserts] = useState([])
  const [spinoffs, setSpinoffs] = useState([]) // [{id, text, minimized, zIndex}]
  const topZRef = useRef(100)
  const composerRef = useRef(null)
  // Lets handleSend flush a just-edited system prompt to the server before
  // the message is posted (SystemPromptEditor persists on blur).
  const promptEditorRef = useRef(null)
  // Guards handleSend against re-entry: the composer stays enabled while
  // handleSend awaits the prompt flush (streaming is still false), so a
  // double-submit would otherwise open two concurrent SSE streams.
  const sendInFlightRef = useRef(false)

  const quoteSelection = useCallback((text) => {
    if (!text) return
    const quoted = text.split('\n').map(line => `> ${line}`).join('\n')
    composerRef.current?.insertText(quoted)
  }, [])

  const critiqueSelection = useCallback((text) => {
    if (!text) return
    const quoted = text.split('\n').map(line => `> ${line}`).join('\n')
    composerRef.current?.insertText(`Please critique the following:\n\n${quoted}`)
  }, [])

  const createSpinoff = useCallback((text) => {
    const id = ++spinoffCounter
    topZRef.current++
    const offset = (spinoffs.filter(s => !s.minimized).length % 5) * 30
    setSpinoffs(prev => [...prev, {
      id,
      text,
      conversationId: null, // set when first message is sent
      minimized: false,
      zIndex: topZRef.current,
      position: { x: 200 + offset, y: 100 + offset },
    }])
  }, [spinoffs])

  const onSpinoffConversationCreated = useCallback((windowId, convId) => {
    setSpinoffs(prev => prev.map(s => s.id === windowId ? { ...s, conversationId: convId } : s))
    onRefreshConversations?.()
  }, [onRefreshConversations])

  const closeSpinoff = useCallback((id) => {
    setSpinoffs(prev => prev.filter(s => s.id !== id))
  }, [])

  const minimizeSpinoff = useCallback((id) => {
    setSpinoffs(prev => prev.map(s => s.id === id ? { ...s, minimized: true } : s))
  }, [])

  const restoreSpinoff = useCallback((id) => {
    topZRef.current++
    setSpinoffs(prev => prev.map(s => s.id === id ? { ...s, minimized: false, zIndex: topZRef.current } : s))
  }, [])

  const focusSpinoff = useCallback((id) => {
    topZRef.current++
    setSpinoffs(prev => prev.map(s => s.id === id ? { ...s, zIndex: topZRef.current } : s))
  }, [])

  // The route points at a conversation whose fetch hasn't resolved yet
  // (direct load, or switching from another conversation). Authoritative
  // over a possibly-stale `conversation`: render loading, never the active
  // chat or the create composer. Otherwise typing would either spawn a
  // different new conversation (codex iter 1) or, worse, send into the
  // previously-loaded chat via its stale sendMessage closure (codex iter 2).
  if (awaitingConversation) {
    return (
      <div className="flex-1 flex items-center justify-center text-fg-subtle">
        <div className="text-center">
          <i className="fa-solid fa-spinner fa-spin text-3xl mb-3 block opacity-40"></i>
          <p>Loading conversation…</p>
        </div>
      </div>
    )
  }

  if (!conversation) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-4">
        <div className="w-full max-w-2xl flex flex-col items-center">
          <i className="fa-solid fa-comments text-6xl mb-5 text-accent-fg/40"></i>
          <h2 className="text-2xl font-semibold text-fg mb-2">Start a new conversation</h2>
          <p className="text-sm text-fg-subtle mb-6 text-center">
            {defaultModelName
              ? <>Type a message below — a chat will be created with <span className="text-fg-muted">{defaultModelName}</span>.</>
              : 'No running model services available. Start a model first.'}
          </p>
          <div className="w-full">
            <ChatInput
              focusKey="empty-state"
              onSend={(msg, images) => onCreateAndSend?.(msg, images)}
              disabled={!defaultModelName}
            />
          </div>
        </div>
      </div>
    )
  }

  const targetMessage = critiqueTarget ? messages.find(m => m.id === critiqueTarget) : null

  // A background run can still be active for this conversation even when we
  // have no local SSE stream (the user navigated away and back, so `streaming`
  // is false but the run kept going server-side). Treat it as an in-pane busy
  // state: block the composer/model/MCP controls and surface Stop, which
  // cancels by conversation id regardless of whether we hold the run stream.
  const activeRun = conversation.active_run
  const hasActiveRun = !!activeRun && (activeRun.status === 'running' || activeRun.status === 'queued')
  const busy = streaming || cancelling || hasActiveRun

  function handleOpenCritique(msgId) {
    setCritiqueTarget(msgId)
  }

  function handleCritique(msgId, extraInstructions) {
    critique(msgId, extraInstructions)
  }

  function handleInsertAnnotation(annotation) {
    setPendingInserts(prev => [...prev, annotation])
  }

  async function handleModelChange(field, value) {
    await updateConversation(conversation.id, { [field]: value })
    onReloadConversation?.(conversation.id)
  }

  function handleSystemPromptChange(field, value) {
    return updateConversation(conversation.id, { [field]: value })
  }

  async function handleSend(msg, images) {
    // Drop a re-entrant submit that lands while we're still awaiting the
    // flush below — otherwise both calls reach onSend with a pre-streaming
    // sendMessage closure and start concurrent streams. Once onSend runs,
    // sendMessage flips `streaming` true and the composer's own disabled
    // guard takes over.
    if (sendInFlightRef.current) return
    sendInFlightRef.current = true
    try {
      // SystemPromptEditor persists on blur; focusing the composer blurs it,
      // so a save — or a chain of them, if the user edited again mid-save —
      // can still be running. flush() resolves only once the prompt is fully
      // persisted, so the backend reads the new prompt for the reply. A
      // failed save is surfaced in the editor and does not block the send.
      await promptEditorRef.current?.flush()
      onSend(msg, images)
      setPendingInserts([])
    } finally {
      sendInFlightRef.current = false
    }
  }

  return (
    <div className="flex-1 flex min-w-0">
      {/* Main chat column */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header bar */}
        <div className="border-b border-border px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4 flex-wrap">
            <ModelSelector
              mainService={conversation.main_service}
              sidekickService={conversation.sidekick_service}
              onChangeMain={v => handleModelChange('main_service', v)}
              onChangeSidekick={v => handleModelChange('sidekick_service', v)}
              disabled={busy}
            />
            <McpToggle
              conversationId={conversation.id}
              enabledServers={conversation.mcp_servers}
              onUpdate={() => onReloadConversation?.(conversation.id)}
              disabled={busy}
            />
          </div>
          {(streaming || hasActiveRun) && !cancelling && (
            <button
              onClick={onStopStreaming}
              className="text-xs px-3 py-1 bg-danger-subtle text-danger-fg border border-danger rounded hover:bg-danger-subtle"
            >
              <i className="fa-solid fa-stop mr-1"></i>Stop
            </button>
          )}
        </div>

        {/* System prompt editor — keyed by conversation so local edit
            state resets cleanly when the user switches conversations. */}
        <SystemPromptEditor
          key={conversation.id}
          ref={promptEditorRef}
          mainPrompt={conversation.main_system_prompt || ''}
          onSaveMain={v => handleSystemPromptChange('main_system_prompt', v)}
        />

        {/* Error display */}
        {error && (
          <div className="mx-4 mt-2 px-3 py-2 bg-danger-subtle border border-danger rounded text-xs text-danger-fg">
            {error}
          </div>
        )}

        {/* Messages */}
        <MessageList
          messages={messages}
          critiques={critiques}
          critiqueLoading={critiqueLoading}
          hasSidekick={!!conversation.sidekick_service}
          onCritique={handleOpenCritique}
          onEdit={onEdit}
          disableEdit={busy}
          streaming={streaming}
          streamingContent={streamingContent}
          streamingReasoning={streamingReasoning}
          toolEvents={toolEvents}
          pendingToolCalls={pendingToolCalls}
          heartbeat={heartbeat}
          artifacts={artifacts}
          streamingArtifacts={streamingArtifacts}
          streamingParseWarning={streamingParseWarning}
          activeCritiqueId={critiqueTarget}
        />

        {/* Input */}
        <ChatInput
          ref={composerRef}
          focusKey={conversation.id}
          onSend={handleSend}
          disabled={busy || !conversation.main_service}
          pendingInserts={pendingInserts}
          onClearInsert={(idx) => setPendingInserts(prev => prev.filter((_, i) => i !== idx))}
        />
      </div>

      {/* Critique panel (right side) */}
      {critiqueTarget && targetMessage && (
        <CritiquePanel
          messageId={critiqueTarget}
          originalContent={targetMessage.content}
          critique={critiques[critiqueTarget]}
          loading={critiqueLoading[critiqueTarget]}
          onCritique={handleCritique}
          onClose={() => setCritiqueTarget(null)}
          onInsertAnnotation={handleInsertAnnotation}
        />
      )}

      {/* Context menu for text selection */}
      <TextContextMenu
        onSpinoff={createSpinoff}
        onQuote={quoteSelection}
        onCritique={critiqueSelection}
      />

      {/* Spinoff windows */}
      {spinoffs.filter(s => !s.minimized).map(s => (
        <SpinoffWindow
          key={s.id}
          id={s.id}
          conversationId={s.conversationId}
          selectedText={s.text}
          serviceName={conversation.main_service}
          parentConversationId={conversation.id}
          position={s.position}
          zIndex={s.zIndex}
          onClose={() => closeSpinoff(s.id)}
          onMinimize={() => minimizeSpinoff(s.id)}
          onFocus={() => focusSpinoff(s.id)}
          onConversationCreated={onSpinoffConversationCreated}
        />
      ))}

      {/* Taskbar for minimized spinoffs */}
      <SpinoffTaskbar
        windows={spinoffs}
        onRestore={restoreSpinoff}
        onClose={closeSpinoff}
      />
    </div>
  )
}
