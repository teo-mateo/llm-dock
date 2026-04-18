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

  if (!conversation) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        <div className="text-center">
          <i className="fa-solid fa-comments text-5xl mb-4 block opacity-20"></i>
          <p>Select or create a conversation</p>
        </div>
      </div>
    )
  }

  const targetMessage = critiqueTarget ? messages.find(m => m.id === critiqueTarget) : null

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

  async function handleSystemPromptChange(field, value) {
    await updateConversation(conversation.id, { [field]: value })
  }

  return (
    <div className="flex-1 flex min-w-0">
      {/* Main chat column */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header bar */}
        <div className="border-b border-gray-700 px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4 flex-wrap">
            <ModelSelector
              mainService={conversation.main_service}
              sidekickService={conversation.sidekick_service}
              onChangeMain={v => handleModelChange('main_service', v)}
              onChangeSidekick={v => handleModelChange('sidekick_service', v)}
              disabled={streaming}
            />
            <McpToggle
              conversationId={conversation.id}
              enabledServers={conversation.mcp_servers}
              onUpdate={() => onReloadConversation?.(conversation.id)}
              disabled={streaming}
            />
          </div>
          {streaming && (
            <button
              onClick={onStopStreaming}
              className="text-xs px-3 py-1 bg-red-600/20 text-red-400 border border-red-600/30 rounded hover:bg-red-600/30"
            >
              <i className="fa-solid fa-stop mr-1"></i>Stop
            </button>
          )}
        </div>

        {/* System prompt editor */}
        <SystemPromptEditor
          mainPrompt={conversation.main_system_prompt || ''}
          sidekickPrompt={conversation.sidekick_system_prompt || ''}
          onChangeMain={v => handleSystemPromptChange('main_system_prompt', v)}
          onChangeSidekick={v => handleSystemPromptChange('sidekick_system_prompt', v)}
        />

        {/* Error display */}
        {error && (
          <div className="mx-4 mt-2 px-3 py-2 bg-red-500/10 border border-red-500/30 rounded text-xs text-red-400">
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
          streaming={streaming}
          streamingContent={streamingContent}
          streamingReasoning={streamingReasoning}
          toolEvents={toolEvents}
          artifacts={artifacts}
          streamingArtifacts={streamingArtifacts}
          activeCritiqueId={critiqueTarget}
        />

        {/* Input */}
        <ChatInput
          onSend={(msg, images) => { onSend(msg, images); setPendingInserts([]) }}
          disabled={streaming || !conversation.main_service}
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
      <TextContextMenu onSpinoff={createSpinoff} />

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
