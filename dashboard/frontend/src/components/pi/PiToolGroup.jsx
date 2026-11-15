import { useMemo, useState } from 'react'
import { moreLabel, toolStatusText, visibleTools } from '../../utils/piToolRuns'
import { parseToolCall } from '../../utils/piTools/payload'
import PiToolDetails from './PiToolDetails'
import { toolEntry, toolSummary } from './tools/toolViews'

function dotClass(status) {
  if (status === 'running') return 'bg-warning animate-pulse'
  if (status === 'error') return 'bg-error'
  return 'bg-success'
}

function PiToolRow({ item }) {
  const [open, setOpen] = useState(false)
  const { name, args, output } = item
  const { parse } = toolEntry(name)
  const parsed = useMemo(() => parseToolCall(args, output, parse), [args, output, parse])
  const tool = { ...parsed, item }
  return (
    <li className="border-b border-border last:border-b-0">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="group flex w-full items-center gap-2 px-3 py-1 text-left hover:bg-surface-muted"
      >
        <span
          role="img"
          aria-label={toolStatusText(item)}
          className={`h-2 w-2 shrink-0 rounded-full ${dotClass(item.status)}`}
        />
        <span className="shrink-0 font-mono text-xs font-semibold text-fg">{item.name}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-fg-muted">
          {toolSummary(tool)}
        </span>
        <span className="shrink-0 text-xs font-semibold text-accent group-hover:underline">
          {open ? 'Hide' : 'Details'}
        </span>
      </button>
      {open && <PiToolDetails tool={tool} />}
    </li>
  )
}

export default function PiToolGroup({ group }) {
  const [expanded, setExpanded] = useState(false)
  const { shown, hidden } = visibleTools(group.tools, expanded)
  return (
    <ul
      aria-label="Tool calls"
      className="overflow-hidden rounded-lg border border-border-strong bg-app"
    >
      {shown.map((item) => (
        <PiToolRow key={item.id} item={item} />
      ))}
      {group.thinking && (
        <li className="animate-pulse px-3 py-1 text-xs text-fg-muted">thinking…</li>
      )}
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
