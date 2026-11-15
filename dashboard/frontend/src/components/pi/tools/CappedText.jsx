import { useState } from 'react'
import { cappedSlice } from './lineCap'
import ShowAllToggle from './ShowAllToggle'

const TONES = {
  fg: 'text-fg',
  muted: 'text-fg-muted',
  error: 'text-danger-fg',
}

export default function CappedText({ text, tone = 'muted', wrap = true, bare = false }) {
  const [expanded, setExpanded] = useState(false)
  const lines = text.split('\n')
  const { capped, shown } = cappedSlice(lines, expanded)
  const layout = wrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre overflow-x-auto'
  const frame = bare ? '' : 'max-h-[32rem] overflow-y-auto rounded border border-border bg-app px-2 py-1'

  return (
    <div className="flex min-w-0 flex-col items-start gap-1">
      <pre className={`m-0 w-full min-w-0 font-mono text-xs ${layout} ${frame} ${TONES[tone]}`}>
        {capped ? shown.join('\n') : text}
      </pre>
      {capped && (
        <ShowAllToggle expanded={expanded} total={lines.length} onToggle={() => setExpanded((value) => !value)} />
      )}
    </div>
  )
}
