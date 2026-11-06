import { useState } from 'react'
import { toolStatusText } from '../../utils/piToolRuns'

const MAX_VISIBLE_LINES = 20

function statusClass(status) {
  if (status === 'running') return 'text-warning-fg'
  if (status === 'error') return 'text-error'
  return 'text-success-fg'
}

export default function PiToolDetails({ item }) {
  const [expanded, setExpanded] = useState(false)
  const output = item.output ?? ''
  const lines = output.split('\n')
  const longOutput = lines.length > MAX_VISIBLE_LINES
  const shown = longOutput && !expanded
    ? lines.slice(0, MAX_VISIBLE_LINES).join('\n')
    : output

  return (
    <div className="flex flex-col gap-2 border-t border-border bg-app px-3 py-2">
      <span className={`text-xs ${statusClass(item.status)}`}>{toolStatusText(item)}</span>

      {item.args != null && (
        <pre className="max-h-60 overflow-auto font-mono text-xs whitespace-pre-wrap break-words text-fg-muted">
          {item.args}
        </pre>
      )}

      {item.output != null && (
        <pre className="max-h-80 overflow-auto rounded border border-border bg-surface px-2 py-1 font-mono text-xs whitespace-pre-wrap break-words text-fg-muted">
          {shown}
        </pre>
      )}

      {longOutput && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="self-start text-xs text-accent hover:underline"
        >
          {expanded ? 'Show less' : 'Show all'}
        </button>
      )}

      {item.truncated && (
        <p className="text-xs text-warning-fg">output truncated by pi-remote</p>
      )}
    </div>
  )
}
