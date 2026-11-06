import { useEffect, useMemo, useRef, useState } from 'react'
import { runEndLabel } from '../../utils/piCommands'
import PiMessage from './PiMessage'
import PiToolGroup from './PiToolGroup'
import { groupToolRuns } from '../../utils/piToolRuns'

const NEAR_BOTTOM_PX = 80

export default function PiTranscript({ items, working, lastStopAt }) {
  const containerRef = useRef(null)
  const [follow, setFollow] = useState(true)
  const [seenItems, setSeenItems] = useState(items)
  const shown = useMemo(() => groupToolRuns(items), [items])
  const unseen = !follow && seenItems !== items

  useEffect(() => {
    const container = containerRef.current
    if (container && follow) container.scrollTop = container.scrollHeight
  }, [items, follow])

  function handleScroll() {
    const container = containerRef.current
    if (!container) return
    const atBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight <= NEAR_BOTTOM_PX
    if (atBottom !== follow) setFollow(atBottom)
    setSeenItems(items)
  }

  function jumpToBottom() {
    setSeenItems(items)
    setFollow(true)
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        aria-busy={working}
        data-testid="pi-transcript"
        className="flex-1 overflow-y-auto"
      >
      <div className="flex flex-col gap-4 py-4">
        {shown.map((item) => {
          if (item.kind === 'user' || item.kind === 'assistant') {
            return <PiMessage key={item.id} item={item} />
          }
          if (item.kind === 'tool_group') {
            return <PiToolGroup key={item.id} group={item} />
          }
          if (item.kind === 'notice') {
            return (
              <p key={item.id} className="text-center text-xs text-fg-muted">
                {item.text}
              </p>
            )
          }
          if (item.kind === 'run_end') {
            return (
              <div key={item.id} className="flex items-center gap-2 text-xs text-fg-muted">
                <span className="h-px flex-1 bg-border"></span>
                <span>{runEndLabel(item.outcome, item.ts, lastStopAt)}</span>
                <span className="h-px flex-1 bg-border"></span>
              </div>
            )
          }
          return null
        })}
      </div>
    </div>
      {unseen && (
        <button
          type="button"
          onClick={jumpToBottom}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border border-border bg-elevated px-3 py-1 text-xs font-semibold text-accent shadow"
        >
          New content ↓
        </button>
      )}
    </div>
  )
}
