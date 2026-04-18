import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeRaw from 'rehype-raw'
import rehypeKatex from 'rehype-katex'
import MessageBubble from './MessageBubble'
import ThinkingBlock from './ThinkingBlock'
import ArtifactRenderer from './ArtifactRenderer'

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
      <div className="max-w-4xl mx-auto space-y-4">
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

        {/* Tool events during streaming */}
        {streaming && toolEvents.length > 0 && (
          <div className="space-y-1.5">
            {toolEvents.map((evt, i) => (
              <div key={i} className="flex justify-start">
                <div className="max-w-[80%]">
                  {/* Reasoning before this tool call */}
                  {evt.type === 'call' && evt.reasoning && (
                    <div className="mb-1">
                      <ThinkingBlock content={evt.reasoning} />
                    </div>
                  )}
                  <div className="rounded px-3 py-2 text-xs border bg-gray-800/50 border-gray-700/50 space-y-1">
                    {evt.type === 'call' ? (
                      <>
                        <div className="text-yellow-400">
                          <i className="fa-solid fa-wrench mr-1.5"></i>
                          <span className="font-mono">{evt.name}</span>
                        </div>
                        {evt.arguments && Object.keys(evt.arguments).length > 0 && (
                          <div className="text-gray-400 font-mono pl-5">
                            {Object.entries(evt.arguments).map(([k, v]) => (
                              <div key={k}><span className="text-gray-500">{k}:</span> {String(v)}</div>
                            ))}
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-green-400">
                        <i className="fa-solid fa-check mr-1.5"></i>
                        <span className="font-mono">{evt.name}</span>
                        <span className="text-gray-300 ml-1">→ <span className="font-mono">{evt.result}</span></span>
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
          <div className="max-w-[80%]">
            {streamingArtifacts.map((art, i) => (
              <ArtifactRenderer key={i} artifact={art} />
            ))}
          </div>
        )}

        {/* Streaming response */}
        {streaming && (
          <div className="flex justify-start">
            <div className="max-w-[80%]">
              <div className="text-[10px] text-gray-500 mb-1">Assistant</div>
              {streamingReasoning && (
                <ThinkingBlock content={streamingReasoning} />
              )}
              {streamingContent ? (
                <div className="rounded-lg px-4 py-3 bg-gray-800 border border-gray-700 text-gray-200">
                  <div className="text-sm prose prose-invert prose-sm max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeKatex]}>
                      {streamingContent}
                    </ReactMarkdown>
                  </div>
                </div>
              ) : !streamingReasoning && toolEvents.length === 0 ? (
                <div className="rounded-lg px-4 py-3 bg-gray-800 border border-gray-700">
                  <div className="flex items-center gap-2 text-sm text-gray-400">
                    <i className="fa-solid fa-spinner fa-spin"></i>
                    <span>Thinking...</span>
                  </div>
                </div>
              ) : null}
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
