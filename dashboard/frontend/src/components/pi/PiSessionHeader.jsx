function sessionName(summary) {
  if (summary.name) return summary.name
  const segments = summary.cwd.split('/').filter(Boolean)
  return segments.length > 0 ? segments[segments.length - 1] : summary.cwd
}

function statusLabel(summary) {
  if (!summary.live) return 'ended'
  return summary.state || 'idle'
}

function badgeClass(status) {
  if (status === 'working') return 'bg-warning-subtle text-warning-fg'
  if (status === 'idle') return 'bg-success-subtle text-success-fg'
  return 'border border-border text-fg-muted'
}

export default function PiSessionHeader({ summary }) {
  const status = statusLabel(summary)
  const meta = [summary.cwd, summary.model, summary.thinking_level].filter(Boolean).join(' · ')
  const contextPercent = summary.context_percent
  const contextWidth = Math.max(0, Math.min(100, contextPercent ?? 0))

  return (
    <header className="flex flex-col gap-3 border-b border-border pb-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="min-w-0 truncate text-xl font-bold text-fg">{sessionName(summary)}</h1>
        <span className={`rounded px-2 py-1 text-xs font-semibold ${badgeClass(status)}`}>
          {status}
        </span>
      </div>

      <p className="break-words font-mono text-xs text-fg-muted">{meta}</p>

      {!summary.live && (
        <p className="text-xs text-fg-muted">
          {summary.end_reason ? `ended · ${summary.end_reason}` : 'ended'}
        </p>
      )}

      {contextPercent != null && (
        <div className="flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded bg-border">
            <div className="h-full bg-accent" style={{ width: `${contextWidth}%` }}></div>
          </div>
          <span className="text-xs text-fg-muted">ctx {Math.round(contextPercent)}%</span>
        </div>
      )}
    </header>
  )
}
