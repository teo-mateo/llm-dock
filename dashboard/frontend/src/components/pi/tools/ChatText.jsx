import { useState } from 'react'
import { cappedSlice } from './lineCap'
import ShowAllToggle from './ShowAllToggle'

export default function ChatText({ text, className = '' }) {
  const [expanded, setExpanded] = useState(false)
  const lines = text.split('\n')
  const { capped, shown } = cappedSlice(lines, expanded)
  return (
    <div className="flex min-w-0 flex-col items-start gap-1">
      <p className={`m-0 w-full min-w-0 whitespace-pre-wrap break-words text-sm text-fg ${className}`}>
        {capped ? shown.join('\n') : text}
      </p>
      {capped && (
        <ShowAllToggle expanded={expanded} total={lines.length} onToggle={() => setExpanded((value) => !value)} />
      )}
    </div>
  )
}
