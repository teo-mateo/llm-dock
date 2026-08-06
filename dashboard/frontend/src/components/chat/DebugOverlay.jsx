import { useEffect, useState } from 'react'

// Low-level conversation viewer (debugging). Renders the raw persisted
// message objects — content, reasoning, tool calls (arguments + result),
// parse warnings, errors — that the markdown view hides. Each message is a
// collapsible card; everything is expanded on open, with expand/collapse-all
// controls for long conversations.
//
// Reads the live `messages` state from useChat, so it reflects the current
// in-memory transcript (including an in-progress stream) with no extra fetch.

function JsonBlock({ value }) {
  const text = typeof value === 'string'
    ? value
    : JSON.stringify(value, null, 2)
  return (
    <pre className="text-xs font-mono text-fg-muted bg-surface border border-border-subtle rounded p-2 overflow-x-auto whitespace-pre-wrap break-words">
      {text}
    </pre>
  )
}

function Field({ label, children }) {
  return (
    <div className="mb-2">
      <div className="text-[10px] font-mono uppercase tracking-wide text-fg-subtle mb-1">{label}</div>
      {children}
    </div>
  )
}

function ToolCallBlock({ tool, index }) {
  return (
    <div className="mb-2">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-mono text-accent-fg">#{index + 1} {tool.name}</span>
        {tool.server_id && (
          <span className="text-[10px] font-mono text-fg-subtle">server: {tool.server_id}</span>
        )}
      </div>
      {/* The complete tool-call object, shown verbatim. */}
      <JsonBlock value={tool} />
    </div>
  )
}

function MessageCard({ message, open, onToggle }) {
  const toolCalls = message.tool_calls && message.tool_calls.length > 0 ? message.tool_calls : null
  const isUser = message.role === 'user'
  return (
    <div className="border border-border rounded mb-3 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-3 py-2 bg-elevated hover:bg-surface-strong text-left"
      >
        <span className={`text-xs font-mono font-semibold px-2 py-0.5 rounded ${
          isUser ? 'bg-accent-subtle text-accent-fg' : 'bg-success-subtle text-success-fg'
        }`}>
          {message.role}
        </span>
        <span className="text-xs font-mono text-fg-muted">seq {message.seq}</span>
        <span className="flex-1 text-xs text-fg-subtle truncate">
          {message.model_service && `via ${message.model_service}`}
        </span>
        <span className="text-[10px] font-mono text-fg-faint">{message.created_at}</span>
        <i className={`fa-solid fa-chevron-${open ? 'up' : 'down'} text-fg-subtle text-xs`} />
      </button>
      {open && (
        <div className="px-3 py-2 border-t border-border">
          {/* Fields are ordered to mirror the model's actual output sequence:
              reasoning (thinking) comes first, then tool calls, then the final
              content. */}
          {message.reasoning_content && (
            <Field label="reasoning_content">
              <div className="text-sm text-fg-muted whitespace-pre-wrap break-words">{message.reasoning_content}</div>
            </Field>
          )}
          {toolCalls && (
            <Field label={`tool_calls (${toolCalls.length})`}>
              {toolCalls.map((t, i) => <ToolCallBlock key={i} tool={t} index={i} />)}
            </Field>
          )}
          <Field label="content">
            {message.content ? (
              <div className="text-sm text-fg whitespace-pre-wrap break-words">{message.content}</div>
            ) : (
              <div className="text-xs font-mono text-fg-faint italic">(empty)</div>
            )}
          </Field>
          {message.parse_warning && (
            <Field label={`parse_warning · ${message.parse_warning.kind}`}>
              <div className="text-xs text-warning-fg mb-1">{message.parse_warning.description}</div>
              {message.parse_warning.snippet && <JsonBlock value={message.parse_warning.snippet} />}
            </Field>
          )}
          {message.error && (
            <Field label="error">
              <div className="text-xs text-danger-fg whitespace-pre-wrap break-words">{message.error}</div>
            </Field>
          )}
        </div>
      )}
    </div>
  )
}

export default function DebugOverlay({ messages, onClose }) {
  // Everything is expanded on open (the overlay mounts fresh each time it is
  // shown). Messages that complete while the overlay is open appear collapsed —
  // acceptable for a debug tool; "Expand all" reveals them.
  const [openIds, setOpenIds] = useState(() => new Set(messages.map(m => m.id)))

  // Esc closes the overlay
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const toggle = (id) => setOpenIds(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const allOpen = messages.length > 0 && openIds.size === messages.length
  const expandAll = () => setOpenIds(new Set(messages.map(m => m.id)))
  const collapseAll = () => setOpenIds(new Set())

  return (
    <div className="fixed inset-0 z-50 bg-overlay/95 overflow-auto">
      <div className="p-4 md:p-6 max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between gap-4 mb-4">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold text-fg">Low-level conversation viewer</h1>
            <div className="text-xs font-mono text-fg-subtle truncate">
              {messages.length} message{messages.length === 1 ? '' : 's'}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={allOpen ? collapseAll : expandAll}
              className="text-xs px-2 py-1 bg-surface border border-border rounded text-fg-muted hover:text-accent transition-colors"
            >
              <i className={`fa-solid ${allOpen ? 'fa-compress' : 'fa-expand'} mr-1`} />
              {allOpen ? 'Collapse all' : 'Expand all'}
            </button>
            <button
              onClick={onClose}
              className="text-xs px-2 py-1 bg-surface border border-border rounded text-fg-muted hover:text-danger transition-colors"
            >
              <i className="fa-solid fa-xmark mr-1" />Close
            </button>
          </div>
        </div>

        {/* Message cards */}
        {messages.length === 0 ? (
          <div className="text-center text-fg-subtle py-16">
            <i className="fa-solid fa-inbox text-4xl mb-3 opacity-40 block" />
            <p className="text-sm">No messages in this conversation yet.</p>
          </div>
        ) : (
          messages.map(m => (
            <MessageCard
              key={m.id}
              message={m}
              open={openIds.has(m.id)}
              onToggle={() => toggle(m.id)}
            />
          ))
        )}
      </div>
    </div>
  )
}
