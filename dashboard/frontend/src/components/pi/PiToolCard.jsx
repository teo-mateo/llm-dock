import { useState } from 'react'

const MAX_VISIBLE_LINES = 20

function statusText(item) {
  if (item.status === 'running') return 'running…'
  if (item.status === 'error') return 'error'
  if (item.durationMs == null) return 'done'
  return `done · ${(item.durationMs / 1000).toFixed(1)} s`
}

function statusClass(status) {
  if (status === 'running') return 'text-warning-fg'
  if (status === 'error') return 'text-error'
  return 'text-success-fg'
}

export default function PiToolCard({ item }) {
  const [expanded, setExpanded] = useState(false)
  const output = item.output ?? ''
  const lines = output.split('\n')
  const longOutput = lines.length > MAX_VISIBLE_LINES
  const shown = longOutput && !expanded
    ? lines.slice(0, MAX_VISIBLE_LINES).join('\n')
    : output

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
        <span className="font-mono text-sm font-semibold text-fg">{item.name}</span>
        <span className={`text-xs ${statusClass(item.status)}`}>{statusText(item)}</span>
      </div>

      {item.args != null && (
        <details className="border-b border-border">
          <summary className="cursor-pointer px-3 py-2 text-xs text-fg-muted">args</summary>
          <pre className="overflow-auto px-3 pb-2 font-mono text-xs text-fg-muted">{item.args}</pre>
        </details>
      )}

      {item.output != null && (
        <pre className="max-h-80 overflow-auto px-3 py-2 font-mono text-xs whitespace-pre-wrap break-words text-fg-muted">
          {shown}
        </pre>
      )}

      {longOutput && (
        <div className="px-3 pb-2">
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="text-xs text-accent hover:underline"
          >
            {expanded ? 'Show less' : 'Show all'}
          </button>
        </div>
      )}

      {item.truncated && (
        <p className="px-3 pb-2 text-xs text-warning-fg">output truncated by pi-remote</p>
      )}
    </div>
  )
}
