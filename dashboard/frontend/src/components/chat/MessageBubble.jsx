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

const MD_COMPONENTS = { pre: CopyablePre }

export default function MessageBubble({ message, critique, critiqueLoading, hasSidekick, onCritique, onEdit, isActiveCritique, artifacts }) {
  const [editing, setEditing] = useState(false)
  const [editValue, setEditValue] = useState(message.content)
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
        className={`absolute left-[10px] top-[7px] w-[9px] h-[9px] rounded-full bg-gray-850 border ${
          isUser ? 'border-accent-strong' : 'border-accent'
        }`}
      ></span>
      <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
        <div className={`max-w-[90%] ${isUser ? 'order-1' : ''}`}>
          {/* Role label — light/minimal, no mono meta line */}
          <div className={`text-[10px] text-gray-500 mb-1 ${isUser ? 'text-right' : ''}`}>
            {isUser ? 'You' : message.model_service || 'Assistant'}
          </div>

        {/* Thinking block for assistant */}
        {!isUser && message.reasoning_content && (
          <ThinkingBlock content={message.reasoning_content} />
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
              <div key={i} className="rounded px-3 py-2 text-xs border bg-gray-800/50 border-gray-700/50 space-y-1">
                <div className="text-yellow-400">
                  <i className="fa-solid fa-wrench mr-1.5"></i>
                  <span className="font-mono">{tc.name}</span>
                </div>
                {tc.arguments && Object.keys(tc.arguments).length > 0 && (
                  <div className="text-gray-400 font-mono pl-5">
                    {Object.entries(tc.arguments).map(([k, v]) => (
                      <div key={k} className="truncate"><span className="text-gray-500">{k}:</span> {formatArgValue(v)}</div>
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
            spine, not a filled rounded bubble. */}
        <div className={`rounded border border-line border-l-2 px-4 py-3 ${
          isUser
            ? 'border-l-accent-strong bg-gray-850 text-gray-100'
            : 'border-l-accent bg-gray-800 text-gray-200'
        } ${isTemp ? 'opacity-70' : ''} ${
          isActiveCritique ? 'ring-2 ring-yellow-500/50' : ''
        }`}>
          {/* Images */}
          {messageImages.length > 0 && (
            <div className="flex gap-2 flex-wrap mb-2">
              {messageImages.map((src, i) => (
                <a key={i} href={src} target="_blank" rel="noopener noreferrer">
                  <img
                    src={src}
                    alt={`Image ${i + 1}`}
                    className="max-w-[300px] max-h-[200px] rounded border border-gray-600 hover:border-gray-400 transition-colors cursor-pointer"
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
                className="w-full min-h-[140px] bg-gray-800 border border-gray-700 text-gray-100 font-mono rounded px-3 py-2 text-sm resize-y focus:outline-none focus:border-accent"
                autoFocus
              />
              <div className="flex gap-2 mt-2 text-xs">
                <button onClick={handleEditSubmit} className="px-2 py-1 bg-blue-500 rounded hover:bg-blue-400">Save</button>
                <button onClick={() => { setEditing(false); setEditValue(message.content) }} className="px-2 py-1 bg-gray-600 rounded hover:bg-gray-500">Cancel</button>
              </div>
            </div>
          ) : isUser ? (
            message.content && <p className="text-sm whitespace-pre-wrap font-mono">{message.content}</p>
          ) : (
            message.content && (
              <div className="prose prose-invert max-w-none text-[15px] leading-relaxed font-serif [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeKatex]} components={MD_COMPONENTS}>
                  {message.content}
                </ReactMarkdown>
              </div>
            )
          )}
        </div>

        {/* Action buttons */}
        {!isTemp && (
          <div className={`flex gap-2 mt-1 opacity-0 group-hover:opacity-100 transition-opacity ${isUser ? 'justify-end' : ''}`}>
            {isUser && !editing && (
              <button
                onClick={() => setEditing(true)}
                className="text-xs text-gray-500 hover:text-gray-400"
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
          </div>
        )}
        </div>
      </div>
    </div>
  )
}
