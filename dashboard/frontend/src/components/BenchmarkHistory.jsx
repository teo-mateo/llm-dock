import { useState } from 'react'

const STATUS_STYLES = {
  pending: 'bg-surface-strong text-fg-muted',
  running: 'bg-accent text-white',
  completed: 'bg-success text-white',
  failed: 'bg-danger text-white',
  cancelled: 'bg-surface-strong text-fg-subtle',
}

function fmtTs(n) {
  if (n == null) return '—'
  return `${n.toFixed(2)} t/s`
}

function fmtTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

export default function BenchmarkHistory({ history, applyingId, deletingId, onApply, onDelete, onExpand }) {
  const [expandedId, setExpandedId] = useState(null)

  const toggle = (run) => {
    const next = expandedId === run.id ? null : run.id
    setExpandedId(next)
    if (next && !run.raw_output && !run.error_message) onExpand(run)
  }

  return (
    <div className="bg-surface rounded-lg border border-border">
      <div className="px-5 py-4 border-b border-border flex justify-between items-center">
        <h3 className="text-lg font-semibold text-fg">History</h3>
        <span className="text-fg-subtle text-xs">{history.length} runs</span>
      </div>

      {history.length === 0 ? (
        <div className="p-5 text-fg-muted text-sm">No benchmark runs recorded for this service yet.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-fg-subtle border-b border-border">
                <th className="px-4 py-2">Date</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">PP t/s</th>
                <th className="px-4 py-2">TG t/s</th>
                <th className="px-4 py-2">Params</th>
                <th className="px-4 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {history.map(run => (
                <RunRow
                  key={run.id}
                  run={run}
                  expanded={expandedId === run.id}
                  onToggle={() => toggle(run)}
                  applying={applyingId === run.id}
                  deleting={deletingId === run.id}
                  onApply={() => onApply(run.id)}
                  onDelete={() => onDelete(run.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function RunRow({ run, expanded, onToggle, applying, deleting, onApply, onDelete }) {
  const paramCount = Object.keys(run.params || {}).length
  const isRunning = run.status === 'running' || run.status === 'pending'

  return (
    <>
      <tr className="border-b border-border/50 hover:bg-surface-strong/40 cursor-pointer" onClick={onToggle}>
        <td className="px-4 py-2 whitespace-nowrap text-fg-muted">{fmtTime(run.created_at)}</td>
        <td className="px-4 py-2">
          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLES[run.status] || STATUS_STYLES.pending}`}>
            {run.status}
          </span>
        </td>
        <td className="px-4 py-2 font-mono text-xs">{fmtTs(run.pp_avg_ts)}</td>
        <td className="px-4 py-2 font-mono text-xs">{fmtTs(run.tg_avg_ts)}</td>
        <td className="px-4 py-2 text-fg-muted">{paramCount}</td>
        <td className="px-4 py-2 text-right whitespace-nowrap" onClick={e => e.stopPropagation()}>
          {run.status === 'completed' && (
            <button
              onClick={onApply}
              disabled={applying}
              className="text-xs px-2 py-1 rounded bg-accent-strong hover:bg-accent text-white font-medium cursor-pointer disabled:opacity-50"
              title="Write this run's non-benchmark flags back onto the service"
            >
              {applying ? 'Applying…' : 'Apply to service'}
            </button>
          )}
          <button
            onClick={onDelete}
            disabled={deleting}
            className="text-xs px-2 py-1 ml-2 rounded bg-surface-strong hover:bg-danger hover:text-white text-fg-muted cursor-pointer disabled:opacity-50"
            title={isRunning ? 'Cancel this run' : 'Delete this run'}
          >
            {deleting ? '…' : isRunning ? 'Cancel' : 'Delete'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border/50 bg-surface-strong/30">
          <td colSpan={6} className="px-4 py-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div>
                <div className="uppercase tracking-wide text-fg-subtle mb-1">Parameters</div>
                <pre className="bg-surface rounded p-2 overflow-x-auto font-mono text-xs text-fg max-h-48 overflow-y-auto">
                  {Object.entries(run.params || {}).map(([flag, value]) => `${flag}${value ? ` ${value}` : ''}`).join('\n') || '(none)'}
                </pre>
              </div>
              <div>
                <div className="uppercase tracking-wide text-fg-subtle mb-1">
                  {run.status === 'failed' ? 'Error' : 'Output'}
                </div>
                {run.status === 'failed' && run.error_message ? (
                  <pre className="bg-surface rounded p-2 font-mono text-xs text-danger-fg max-h-48 overflow-y-auto whitespace-pre-wrap">{run.error_message}</pre>
                ) : (
                  <pre className="bg-surface rounded p-2 font-mono text-xs text-fg-muted max-h-48 overflow-y-auto whitespace-pre-wrap">
                    {run.raw_output || (run.status === 'completed' ? '(no raw output stored)' : 'Not finished yet')}
                  </pre>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
