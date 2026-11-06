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
  return 'bg-surface-muted text-fg-muted'
}

function dotClass(status) {
  if (status === 'working') return 'bg-warning animate-pulse'
  if (status === 'idle') return 'bg-success'
  return 'bg-fg-subtle'
}

export default function PiSessionHeader({ summary, onBack }) {
  const status = statusLabel(summary)
  const contextPercent = summary.context_percent
  const contextWidth = Math.max(0, Math.min(100, contextPercent ?? 0))

  return (
    <header className="flex flex-col gap-2 border-b border-border px-4 py-3 md:px-6 md:py-4">
      <div className="flex items-center gap-3">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="-ml-1 rounded px-1 text-sm font-semibold text-accent-fg md:hidden"
          >
            ‹ Sessions
          </button>
        )}
        <h1 className="min-w-0 truncate text-lg font-semibold text-fg">{sessionName(summary)}</h1>
        <span
          className={`inline-flex flex-none items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${badgeClass(status)}`}
        >
          <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${dotClass(status)}`}></span>
          {status}
        </span>
        {!summary.live && summary.end_reason && (
          <span className="flex-none text-xs text-fg-subtle">{summary.end_reason}</span>
        )}
        {contextPercent != null && (
          <div className="ml-auto flex flex-none items-center gap-2">
            <div className="h-1.5 w-12 overflow-hidden rounded-full bg-surface-muted sm:w-24">
              <div className="h-full rounded-full bg-accent" style={{ width: `${contextWidth}%` }}></div>
            </div>
            <span className="text-xs tabular-nums text-fg-muted">ctx {Math.round(contextPercent)}%</span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-muted">
        <span className="min-w-0 truncate font-mono">{summary.cwd}</span>
        {summary.model && <span className="min-w-0 truncate">{summary.model}</span>}
        {summary.thinking_level && <span>thinking {summary.thinking_level}</span>}
      </div>
    </header>
  )
}
