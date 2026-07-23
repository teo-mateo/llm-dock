import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeRaw from 'rehype-raw'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import ThinkingBlock from './ThinkingBlock'
import CritiqueButton from './CritiqueButton'
import ArtifactRenderer from './ArtifactRenderer'
import CopyablePre from './CopyablePre'
import { formatArgValue } from './toolCallUtils'
import ToolResultBlock from './ToolResultBlock'
import FormatDriftChip from './FormatDriftChip'
import { detectFormatDrift } from './formatDrift'
import useProseClass from '../../hooks/useProseClass'
import { formatModelLabel } from '../../utils/openrouter'

const MD_COMPONENTS = {
  pre: CopyablePre,
  a: (props) => {
    const isExternal = props.href && /^https?:\/\//.test(props.href)
    return isExternal ? (
      <a {...props} target="_blank" rel="noopener noreferrer" />
    ) : (
      <a {...props} />
    )
  },
}

export default function MessageBubble({ message, critique, critiqueLoading, hasSidekick, onCritique, onEdit, onDelete, isActiveCritique, artifacts, disableEdit, disableDelete }) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState(message.content)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const proseClass = useProseClass('max-w-none', 'text-[15px]', 'leading-relaxed', 'font-serif', '[&>*:first-child]:mt-0', '[&>*:last-child]:mb-0')
  const isUser = message.role === 'user'
  const isTemp = message.id?.startsWith('temp-')
  const messageImages = message.images || []
  // Prefer the server-persisted warning. Fall back to a client-side scan for
  // backfill of pre-existing messages whose row doesn't have parse_warning_json.
  const parseWarning = !isUser ? (message.parse_warning || detectFormatDrift(message)) : null

  function handleEditSubmit() {
    const trimmed = editValue.trim()
    if (trimmed && trimmed !== message.content) {
      onEdit?.(message.id, trimmed)
    }
    setEditing(false)
  }

  function handleEditKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleEditSubmit()
    }
    if (e.key === 'Escape') {
      setEditing(false)
      setEditValue(message.content)
    }
  }

  return (
    <div className="relative pl-8 group">
      {/* Timeline tick node — sits in the left gutter on the shared spine. */}
      <span
        aria-hidden="true"
        className={`absolute left-[10px] top-[7px] w-[9px] h-[9px] rounded-full bg-elevated border ${
          isUser ? 'border-accent-strong' : 'border-accent'
        }`}
      ></span>
      <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
        <div className={`max-w-[90%] ${isUser ? 'order-1' : ''}`}>
          {/* Role label — light/minimal, no mono meta line */}
          <div className={`text-[10px] text-fg-subtle mb-1 ${isUser ? 'text-right' : ''}`}>
            {isUser ? 'You' : formatModelLabel(message.model_service) || 'Assistant'}
          </div>

        {/* Thinking block for assistant */}
        {!isUser && message.reasoning_content && (
          <ThinkingBlock content={message.reasoning_content} />
        )}

        {/* Error banner — shown when the model errored mid-generation */}
        {!isUser && message.error && (
          <div className="mb-2 rounded px-3 py-2 text-xs border border-danger bg-danger-subtle text-danger-fg">
            <i className="fa-solid fa-triangle-exclamation mr-1.5"></i>
            Generation failed: {message.error}
          </div>
        )}

        {/* Format-drift chip — flags Qwen3.6-style failure modes. Prefers
            persisted warning, falls back to client-side detection so older
            messages without parse_warning_json still surface a chip. */}
        {parseWarning && (
          <FormatDriftChip warning={parseWarning} rawContent={message.content} />
        )}

        {/* Tool calls (persisted) */}
        {!isUser && message.tool_calls && message.tool_calls.length > 0 && (
          <div className="mb-2 space-y-1.5">
            {message.tool_calls.map((tc, i) => (
              <div key={i} className="rounded px-3 py-2 text-xs border bg-surface-muted border-border space-y-1">
                <div className="text-warning-fg">
                  <i className="fa-solid fa-wrench mr-1.5"></i>
                  <span className="font-mono">{tc.name}</span>
                </div>
                {tc.arguments && Object.keys(tc.arguments).length > 0 && (
                  <div className="text-fg-muted font-mono pl-5">
                    {Object.entries(tc.arguments).map(([k, v]) => (
                      <div key={k} className="truncate"><span className="text-fg-subtle">{k}:</span> {formatArgValue(v)}</div>
                    ))}
                  </div>
                )}
                {tc.result && (
                  <div className="pl-5">
                    <ToolResultBlock text={tc.result} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Artifacts (before text content, matching streaming order) */}
        {!isUser && artifacts && artifacts.length > 0 && (
          <div className="space-y-2">
            {artifacts.map((art, idx) => (
              <ArtifactRenderer key={art.id || idx} artifact={art} />
            ))}
          </div>
        )}

        {/* Message content — hairline block with a colored left accent
            spine, not a filled rounded bubble. Only render if there's
            content, images, or we're in edit mode. */}
        {(message.content || messageImages.length > 0 || editing) && (
        <div className={`rounded border border-hairline border-l-2 px-4 py-3 ${
          isUser
            ? 'border-l-accent-strong bg-elevated text-fg'
            : 'border-l-accent bg-surface text-fg'
        } ${isTemp ? 'opacity-70' : ''} ${
          isActiveCritique ? 'ring-2 ring-warning/50' : ''
        }`}>
          {/* Images */}
          {messageImages.length > 0 && (
            <div className="flex gap-2 flex-wrap mb-2">
              {messageImages.map((src, i) => (
                <a key={i} href={src} target="_blank" rel="noopener noreferrer">
                  <img
                    src={src}
                    alt={`Image ${i + 1}`}
                    className="max-w-[300px] max-h-[200px] rounded border border-border-strong hover:border-fg-muted transition-colors cursor-pointer"
                  />
                </a>
              ))}
            </div>
          )}

          {/* Text content */}
          {editing ? (
            <div className="w-[60vw] max-w-[800px]">
              <textarea
                value={editValue}
                onChange={e => setEditValue(e.target.value)}
                onKeyDown={handleEditKeyDown}
                rows={6}
                className="w-full min-h-[140px] bg-surface border border-border text-fg font-mono rounded px-3 py-2 text-sm resize-y focus:outline-none focus:border-accent"
                autoFocus
              />
              <div className="flex gap-2 mt-2 text-xs">
                <button onClick={handleEditSubmit} className="px-2 py-1 bg-accent-strong text-fg-inverse rounded hover:bg-accent-hover">Save</button>
                <button onClick={() => { setEditing(false); setEditValue(message.content) }} className="px-2 py-1 bg-border-strong rounded hover:bg-border-strong">Cancel</button>
              </div>
            </div>
          ) : isUser ? (
            message.content && <p className="text-sm whitespace-pre-wrap font-mono">{message.content}</p>
          ) : (
            message.content && (
              <div className={proseClass}>
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeKatex]} components={MD_COMPONENTS}>
                  {message.content}
                </ReactMarkdown>
              </div>
            )
           )}
        </div>
        )}

        {/* Action buttons */}
        {!isTemp && (
          <div className={`flex gap-2 mt-1 ${confirmingDelete ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity ${isUser ? 'justify-end' : ''}`}>
            {isUser && !editing && !disableEdit && (
              <button
                onClick={() => setEditing(true)}
                className="text-xs text-fg-subtle hover:text-fg-muted"
              >
                <i className="fa-solid fa-pen-to-square mr-1"></i>Edit
              </button>
            )}
            {!isUser && hasSidekick && (
              <CritiqueButton
                messageId={message.id}
                hasCritique={!!critique}
                loading={critiqueLoading}
                onClick={onCritique}
              />
            )}
            {!disableDelete && confirmingDelete ? (
              <>
                <button
                  onClick={() => { onDelete?.(message.id); setConfirmingDelete(false) }}
                  className="text-xs px-1.5 py-0.5 bg-danger rounded text-white"
                >Yes</button>
                <button
                  onClick={() => setConfirmingDelete(false)}
                  className="text-xs px-1.5 py-0.5 bg-surface-strong rounded text-fg"
                >No</button>
              </>
            ) : (
              !disableDelete && (
                <button
                  onClick={() => setConfirmingDelete(true)}
                  className="text-xs text-fg-subtle hover:text-danger-fg"
                  title="Delete message"
                >
                  <i className="fa-solid fa-trash mr-1"></i>Delete
                </button>
              )
            )}
          </div>
        )}
        </div>
      </div>
    </div>
  )
}
