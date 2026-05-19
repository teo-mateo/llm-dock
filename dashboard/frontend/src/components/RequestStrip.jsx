export default function RequestStrip({ running, waiting, preemptRate }) {
  const fmt = (val) => val !== undefined && val != null ? val : '—'

  return (
    <div className="bg-surface rounded-lg border border-border p-4">
      <h3 className="text-sm font-medium text-fg-muted mb-3">Requests</h3>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <span className="flex items-center gap-1.5 text-fg-muted">
          <i className="fa-solid fa-bolt text-warning-fg text-xs" />
          Running: <span className="font-mono font-semibold">{fmt(running)}</span>
        </span>
        <span className="text-fg-faint">|</span>
        <span className="flex items-center gap-1.5 text-fg-muted">
          <i className="fa-solid fa-clock text-accent-fg text-xs" />
          Waiting: <span className="font-mono font-semibold">{fmt(waiting)}</span>
        </span>
        <span className="text-fg-faint">|</span>
        <span className="flex items-center gap-1.5 text-fg-muted">
          <i className="fa-solid fa-arrows-rotate text-danger-fg text-xs" />
          Preempt: <span className="font-mono font-semibold">{typeof preemptRate === 'number' ? preemptRate.toFixed(1) : fmt(preemptRate)}</span>
          {typeof preemptRate === 'number' && <span className="text-fg-subtle text-xs">/s</span>}
        </span>
      </div>
    </div>
  )
}
