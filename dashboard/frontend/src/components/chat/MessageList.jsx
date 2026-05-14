import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeRaw from 'rehype-raw'
import rehypeKatex from 'rehype-katex'
import MessageBubble from './MessageBubble'
import ThinkingBlock from './ThinkingBlock'
import ArtifactRenderer from './ArtifactRenderer'
import CopyablePre from './CopyablePre'
import { formatArgValue } from './toolCallUtils'
import ToolResultBlock from './ToolResultBlock'

const MD_COMPONENTS = { pre: CopyablePre }

export default function MessageList({
  messages,
  critiques,
  critiqueLoading,
  hasSidekick,
  onCritique,
  onEdit,
  streaming,
  streamingContent,
  streamingReasoning,
  toolEvents = [],
  pendingToolCalls = [],
  heartbeat = null,
  artifacts = {},
  streamingArtifacts = [],
  activeCritiqueId,
}) {
  const bottomRef = useRef(null)
  const containerRef = useRef(null)
  const userScrolledRef = useRef(false)

  // Auto-scroll on new content
  useEffect(() => {
    if (!userScrolledRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, streamingContent, streamingReasoning])

  function handleScroll() {
    const el = containerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
    userScrolledRef.current = !atBottom
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex-1 overflow-auto p-4 space-y-4"
    >
      <div className="max-w-6xl mx-auto space-y-4">
        {messages.map(msg => (
          <MessageBubble
            key={msg.id}
            message={msg}
            critique={critiques[msg.id]}
            critiqueLoading={critiqueLoading[msg.id]}
            hasSidekick={hasSidekick}
            onCritique={onCritique}
            onEdit={onEdit}
            isActiveCritique={activeCritiqueId === msg.id}
            artifacts={artifacts[msg.id]}
          />
        ))}

        {/* Assistant header + continuous thinking trace — renders ABOVE the
            tool events so the visual order matches the saved view (one
            Thinking block at top, then tool calls). streamingReasoning is
            never cleared on tool_call now; it grows across all rounds. */}
        {streaming && (toolEvents.length > 0 || streamingReasoning) && (
          <div className="flex justify-start">
            <div className="max-w-[90%]">
              <div className="text-[10px] text-gray-500 mb-1">Assistant</div>
              {streamingReasoning && (
                <ThinkingBlock content={streamingReasoning} />
              )}
            </div>
          </div>
        )}

        {/* Tool events during streaming */}
        {streaming && toolEvents.length > 0 && (
          <div className="space-y-1.5">
            {toolEvents.map((evt, i) => (
              <div key={i} className="flex justify-start">
                <div className="max-w-[90%]">
                  <div className="rounded px-3 py-2 text-xs border bg-gray-800/50 border-gray-700/50 space-y-1">
                    <div className={'result' in evt ? 'text-green-400' : 'text-yellow-400'}>
                      <i className={`fa-solid ${'result' in evt ? 'fa-check' : 'fa-wrench fa-fade'} mr-1.5`}></i>
                      <span className="font-mono">{evt.name}</span>
                      {!('result' in evt) && (
                        <span className="ml-2 text-[10px] uppercase tracking-wide text-gray-500">running…</span>
                      )}
                    </div>
                    {evt.arguments && Object.keys(evt.arguments).length > 0 && (
                      <div className="text-gray-400 font-mono pl-5">
                        {Object.entries(evt.arguments).map(([k, v]) => (
                          <div key={k} className="truncate"><span className="text-gray-500">{k}:</span> {formatArgValue(v)}</div>
                        ))}
                      </div>
                    )}
                    {'result' in evt && (
                      <div className="pl-5">
                        <ToolResultBlock text={evt.result} />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Streaming artifacts — show as soon as they arrive, before the response */}
        {streaming && streamingArtifacts.length > 0 && (
          <div className="max-w-[90%]">
            {streamingArtifacts.map((art, i) => (
              <ArtifactRenderer key={i} artifact={art} />
            ))}
          </div>
        )}

        {/* Pending tool call pills — model has started naming a tool but
            hasn't finished assembling the call yet. Replaced by the full
            panel in toolEvents once finish_reason==tool_calls lands. */}
        {streaming && pendingToolCalls.length > 0 && (
          <div className="space-y-1.5">
            {pendingToolCalls.map((p) => (
              <div key={p.index} className="flex justify-start">
                <div className="max-w-[90%]">
                  <div className="rounded px-3 py-2 text-xs border bg-gray-800/30 border-gray-700/50 border-dashed flex items-center gap-2 text-yellow-400/80">
                    <i className="fa-solid fa-wrench fa-fade"></i>
                    <span className="font-mono">{p.name || 'tool'}</span>
                    <span className="text-gray-500">assembling call…</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Streaming response — only the content/fallback. The Assistant
            header + reasoning render above (alongside tool events). */}
        {streaming && (
          <div className="flex justify-start">
            <div className="max-w-[90%]">
              {!toolEvents.length && !streamingReasoning && (
                <div className="text-[10px] text-gray-500 mb-1">Assistant</div>
              )}
              {streamingContent ? (
                <div className="rounded-lg px-4 py-3 bg-gray-800 border border-gray-700 text-gray-200">
                  <div className="text-sm prose prose-invert prose-sm max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeKatex]} components={MD_COMPONENTS}>
                      {streamingContent}
                    </ReactMarkdown>
                  </div>
                </div>
              ) : !streamingReasoning && toolEvents.length === 0 && pendingToolCalls.length === 0 ? (
                <div className="rounded-lg px-4 py-3 bg-gray-800 border border-gray-700">
                  <div className="flex items-center gap-2 text-sm text-gray-400">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-60"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                    </span>
                    <span>
                      {heartbeat
                        ? `Waiting for model… ${heartbeat.elapsed_s.toFixed(1)}s`
                        : 'Thinking…'}
                    </span>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        )}

        {/* Live heartbeat ribbon — shown whenever the SSE pipe has been idle
            and the "Thinking…" panel above isn't already displayed (because
            partial content / reasoning / tool events are already on screen).
            Covers between-tool-round gaps and reasoning-without-content phases. */}
        {streaming && heartbeat && (streamingContent || streamingReasoning || toolEvents.length > 0 || pendingToolCalls.length > 0) && (
          <div className="flex justify-start">
            <div className="text-[11px] text-gray-500 flex items-center gap-2 pl-1">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-60"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500"></span>
              </span>
              <span>Waiting for model… {heartbeat.elapsed_s.toFixed(1)}s</span>
            </div>
          </div>
        )}

        {/* Empty state */}
        {messages.length === 0 && !streaming && (
          <div className="text-center text-gray-500 py-20">
            <i className="fa-solid fa-comments text-4xl mb-4 block opacity-30"></i>
            <p>Start a conversation</p>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
