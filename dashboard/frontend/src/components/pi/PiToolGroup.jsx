import { useState } from 'react'
import { argsSummary, toolStatusText } from '../../utils/piToolRuns'
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
      <div className="flex items-center gap-2 px-3 py-2">
        <span
          role="img"
          aria-label={toolStatusText(item)}
          className={`h-2 w-2 shrink-0 rounded-full ${dotClass(item.status)}`}
        />
        <span className="shrink-0 font-mono text-sm font-semibold text-fg">{item.name}</span>
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
  return (
    <ul
      aria-label="Tool calls"
      className="overflow-hidden rounded-lg border border-border bg-surface"
    >
      {group.tools.map((item) => (
        <PiToolRow key={item.id} item={item} />
      ))}
    </ul>
  )
}
