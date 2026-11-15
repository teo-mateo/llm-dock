import { toolStatusText } from '../../../utils/piToolRuns'

function statusClass(status) {
  if (status === 'running') return 'text-warning-fg'
  if (status === 'error') return 'text-danger-fg'
  return 'text-fg-muted'
}

export default function ToolMeta({ item, children }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs">
      {children}
      <span className={statusClass(item.status)}>{toolStatusText(item)}</span>
    </div>
  )
}
