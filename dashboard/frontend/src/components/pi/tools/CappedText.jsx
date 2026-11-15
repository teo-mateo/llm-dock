import { useState } from 'react'

const MAX_VISIBLE_LINES = 20

const TONES = {
  fg: 'text-fg',
  muted: 'text-fg-muted',
  error: 'text-danger-fg',
}

export default function CappedText({ text, tone = 'muted', wrap = true, bare = false }) {
  const [expanded, setExpanded] = useState(false)
  const lines = text.split('\n')
  const capped = lines.length > MAX_VISIBLE_LINES
  const shown = capped && !expanded ? lines.slice(0, MAX_VISIBLE_LINES).join('\n') : text
  const layout = wrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre overflow-x-auto'
  const frame = bare ? '' : 'max-h-[32rem] overflow-y-auto rounded border border-border bg-app px-2 py-1'

  return (
    <div className="flex min-w-0 flex-col items-start gap-1">
      <pre className={`m-0 w-full min-w-0 font-mono text-xs ${layout} ${frame} ${TONES[tone]}`}>
        {shown}
      </pre>
      {capped && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="text-xs text-accent-fg hover:underline"
        >
          {expanded ? 'Show less' : `Show all ${lines.length} lines`}
        </button>
      )}
    </div>
  )
}
