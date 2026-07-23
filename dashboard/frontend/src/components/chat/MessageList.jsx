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
import FormatDriftChip from './FormatDriftChip'
import useProseClass from '../../hooks/useProseClass'

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

export default function MessageList({
  messages,
  critiques,
  critiqueLoading,
  hasSidekick,
  onCritique,
  onEdit,
  onDelete,
  disableEdit,
  disableDelete,
  streaming,
  streamingContent,
  streamingReasoning,
  toolEvents = [],
  pendingToolCalls = [],
  heartbeat = null,
  artifacts = {},
  streamingArtifacts = [],
  streamingParseWarning = null,
  activeCritiqueId,
}) {
  const bottomRef = useRef(null)
  const containerRef = useRef(null)
  const userScrolledRef = useRef(false)
  const proseClass = useProseClass('max-w-none', 'text-[15px]', 'leading-relaxed', 'font-serif', '[&>*:first-child]:mt-0', '[&>*:last-child]:mb-0')

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
      <div className="relative max-w-6xl mx-auto space-y-4">
        {/* Timeline spine — a hairline rule down the left gutter with
            faded ends; per-turn tick nodes sit on it (rendered per turn). */}
        {(messages.length > 0 || streaming) && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-[14px] top-1 bottom-6 w-px"
            style={{
              background:
                'linear-gradient(180deg, transparent, var(--color-hairline-strong) 4%, var(--color-hairline-strong) 96%, transparent)',
            }}
          ></div>
        )}
        {messages.map(msg => (
          <MessageBubble
            key={msg.id}
            message={msg}
            critique={critiques[msg.id]}
            critiqueLoading={critiqueLoading[msg.id]}
            hasSidekick={hasSidekick}
            onCritique={onCritique}
            onEdit={onEdit}
            onDelete={onDelete}
            disableEdit={disableEdit}
            disableDelete={disableDelete}
            isActiveCritique={activeCritiqueId === msg.id}
            artifacts={artifacts[msg.id]}
          />
        ))}

        {/* Streaming assistant turn — one timeline node for the whole
            in-flight turn, aligned to the shared spine via the gutter. */}
        {streaming && (
        <div className="relative pl-8 space-y-4">
          <span
            aria-hidden="true"
            className="absolute left-[10px] top-[7px] w-[9px] h-[9px] rounded-full bg-elevated border border-accent"
          ></span>

        {/* Assistant header + continuous thinking trace — renders ABOVE the
            tool events so the visual order matches the saved view (one
            Thinking block at top, then tool calls). streamingReasoning is
            never cleared on tool_call now; it grows across all rounds. */}
        {streaming && (toolEvents.length > 0 || streamingReasoning) && (
          <div className="flex justify-start">
            <div className="max-w-[90%]">
              <div className="text-[10px] text-fg-subtle mb-1">Assistant</div>
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
                  <div className="rounded px-3 py-2 text-xs border bg-surface-muted border-border space-y-1">
                    <div className={'result' in evt ? 'text-success-fg' : 'text-warning-fg'}>
                      <i className={`fa-solid ${'result' in evt ? 'fa-check' : 'fa-wrench fa-fade'} mr-1.5`}></i>
                      <span className="font-mono">{evt.name}</span>
                      {!('result' in evt) && (
                        <span className="ml-2 text-[10px] uppercase tracking-wide text-fg-subtle">running…</span>
                      )}
                    </div>
                    {evt.arguments && Object.keys(evt.arguments).length > 0 && (
                      <div className="text-fg-muted font-mono pl-5">
                        {Object.entries(evt.arguments).map(([k, v]) => (
                          <div key={k} className="truncate"><span className="text-fg-subtle">{k}:</span> {formatArgValue(v)}</div>
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
                  <div className="rounded px-3 py-2 text-xs border bg-surface-muted border-border border-dashed flex items-center gap-2 text-warning-fg">
                    <i className="fa-solid fa-wrench fa-fade"></i>
                    <span className="font-mono">{p.name || 'tool'}</span>
                    <span className="text-fg-subtle">assembling call…</span>
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
                <div className="text-[10px] text-fg-subtle mb-1">Assistant</div>
              )}
              {streamingParseWarning && (
                <FormatDriftChip warning={streamingParseWarning} rawContent={streamingContent} />
              )}
              {streamingContent ? (
                <div className="rounded border border-hairline border-l-2 border-l-accent px-4 py-3 bg-surface text-fg">
                  <div className={proseClass}>
                    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeKatex]} components={MD_COMPONENTS}>
                      {streamingContent}
                    </ReactMarkdown>
                  </div>
                </div>
              ) : !streamingReasoning && toolEvents.length === 0 && pendingToolCalls.length === 0 ? (
                <div className="rounded border border-hairline border-l-2 border-l-accent px-4 py-3 bg-surface">
                  <div className="flex items-center gap-2 text-sm text-fg-muted">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-accent"></span>
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
            <div className="text-[11px] text-fg-subtle flex items-center gap-2 pl-1">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-accent"></span>
              </span>
              <span>Waiting for model… {heartbeat.elapsed_s.toFixed(1)}s</span>
            </div>
          </div>
        )}
        </div>
        )}

        {/* Empty state */}
        {messages.length === 0 && !streaming && (
          <div className="text-center text-fg-subtle py-20">
            <i className="fa-solid fa-comments text-4xl mb-4 block opacity-30"></i>
            <p>Start a conversation</p>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
