import { useState } from 'react'
import { argsSummary, moreLabel, toolStatusText, visibleTools } from '../../utils/piToolRuns'
import PiToolDetails from './PiToolDetails'

function dotClass(status) {
  if (status === 'running') return 'bg-warning animate-pulse'
  if (status === 'error') return 'bg-error'
  return 'bg-success'
}

function PiToolRow({ item }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="border-b border-border last:border-b-0">
      <div className="flex items-center gap-2 px-3 py-1">
        <span
          role="img"
          aria-label={toolStatusText(item)}
          className={`h-2 w-2 shrink-0 rounded-full ${dotClass(item.status)}`}
        />
        <span className="shrink-0 font-mono text-xs font-semibold text-fg">{item.name}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-fg-muted">
          {argsSummary(item.args)}
        </span>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="shrink-0 text-xs font-semibold text-accent hover:underline"
        >
          Details
        </button>
      </div>
      {open && <PiToolDetails item={item} />}
    </li>
  )
}

export default function PiToolGroup({ group }) {
  const [expanded, setExpanded] = useState(false)
  const { shown, hidden } = visibleTools(group.tools, expanded)
  return (
    <ul
      aria-label="Tool calls"
      className="overflow-hidden rounded-lg border border-border bg-surface"
    >
      {shown.map((item) => (
        <PiToolRow key={item.id} item={item} />
      ))}
      {hidden > 0 && (
        <li>
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="w-full px-3 py-1 text-left text-xs text-fg-muted hover:text-fg"
          >
            {moreLabel(hidden)}
          </button>
        </li>
      )}
    </ul>
  )
}
