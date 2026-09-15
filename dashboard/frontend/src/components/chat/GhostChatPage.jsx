import { useState } from 'react'
import MessageList from './MessageList'
import ChatInput from './ChatInput'
import ModelSelector from './ModelSelector'
import McpToggle from './McpToggle'
import useGhostChat from '../../hooks/useGhostChat'

/**
 * Ghost chat: an ephemeral conversation that leaves no trace. The page keeps
 * every message in React state only (useGhostChat), talks to the stateless
 * /api/chat/ghost endpoint, and never touches localStorage or the
 * conversation APIs — a refresh or tab close erases the thread by design.
 * There is no sidebar entry for an in-flight ghost chat: this route is the
 * only way in, and it is entered with { replace: true } so it does not
 * become a "go back" destination.
 */
export default function GhostChatPage() {
  const [model, setModel] = useState('')
  const [mcpServers, setMcpServers] = useState([])

  const {
    messages,
    streaming,
    streamingContent,
    streamingReasoning,
    toolEvents,
    streamingArtifacts,
    error,
    sendMessage,
    stopStreaming,
  } = useGhostChat()

  async function handleSend(content, images) {
    await sendMessage(content, images, { serviceName: model, mcpServers })
  }

  return (
    <div className="flex flex-col h-screen bg-surface-base">
      {/* Ephemeral-mode banner: the one thing the page must never fail to
          communicate, so it sits above the header, not inside it. */}
      <div className="flex items-center gap-2 px-4 py-2 bg-warning-subtle border-b border-warning text-xs text-warning-fg">
        <i className="fa-solid fa-ghost"></i>
        <span>Ghost mode — nothing is saved. Close the tab to erase.</span>
      </div>

      {/* Header: model + MCP toggles (in-memory), Stop while streaming. */}
      <div className="border-b border-border px-4 py-3 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4 flex-wrap">
          <ModelSelector
            variant="new-chat"
            mainService={model}
            onChangeMain={setModel}
            disabled={streaming}
          />
          <McpToggle
            enabledServers={mcpServers}
            onChange={setMcpServers}
            disabled={streaming}
          />
        </div>
        {streaming && (
          <button
            onClick={stopStreaming}
            className="text-xs px-3 py-1 bg-danger-subtle text-danger-fg border border-danger rounded hover:bg-danger-subtle"
          >
            <i className="fa-solid fa-stop mr-1"></i>Stop
          </button>
        )}
      </div>

      {error && (
        <div className="mx-4 mt-2 px-3 py-2 bg-danger-subtle border border-danger rounded text-xs text-danger-fg">
          {error}
        </div>
      )}

      <MessageList
        messages={messages}
        critiques={{}}
        critiqueLoading={{}}
        hasSidekick={false}
        streaming={streaming}
        streamingContent={streamingContent}
        streamingReasoning={streamingReasoning}
        toolEvents={toolEvents}
        pendingToolCalls={[]}
        heartbeat={null}
        artifacts={{}}
        streamingArtifacts={streamingArtifacts}
        streamingParseWarning={null}
      />

      <ChatInput
        focusKey="ghost"
        onSend={handleSend}
        disabled={streaming || !model}
      />
    </div>
  )
}
