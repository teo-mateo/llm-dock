import { useEffect, useRef } from 'react'
import { runEndLabel } from '../../utils/piCommands'
import PiMessage from './PiMessage'
import PiToolCard from './PiToolCard'

const NEAR_BOTTOM_PX = 80

export default function PiTranscript({ items, working, lastStopAt }) {
  const containerRef = useRef(null)
  const nearBottomRef = useRef(true)
  const itemCountRef = useRef(items.length)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    if (items.length > itemCountRef.current && nearBottomRef.current) {
      container.scrollTop = container.scrollHeight
    }
    itemCountRef.current = items.length
  }, [items.length])

  function handleScroll() {
    const container = containerRef.current
    if (!container) return
    nearBottomRef.current =
      container.scrollHeight - container.scrollTop - container.clientHeight <= NEAR_BOTTOM_PX
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      aria-busy={working}
      className="flex-1 overflow-y-auto"
    >
      <div className="flex flex-col gap-4 py-4">
        {items.map((item) => {
          if (item.kind === 'user' || item.kind === 'assistant') {
            return <PiMessage key={item.id} item={item} />
          }
          if (item.kind === 'tool') {
            return <PiToolCard key={item.id} item={item} />
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
  )
}
