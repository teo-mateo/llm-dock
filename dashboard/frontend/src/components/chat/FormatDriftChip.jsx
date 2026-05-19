import { useState } from 'react'
import { DRIFT_KIND_LABEL } from './formatDrift'

export default function FormatDriftChip({ warning, rawContent }) {
  const [open, setOpen] = useState(false)
  if (!warning) return null
  const label = DRIFT_KIND_LABEL[warning.kind] || warning.kind || 'format drift'
  const hasRaw = typeof rawContent === 'string' && rawContent.length > 0
  return (
    <div className="mt-1 mb-2">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="inline-flex items-center gap-1.5 rounded border border-warning bg-warning-subtle px-2 py-0.5 text-[11px] text-warning-fg hover:bg-warning-subtle"
        title="Click to inspect"
      >
        <i className={`fa-solid fa-triangle-exclamation`}></i>
        <span>{label}</span>
        <i className={`fa-solid ${open ? 'fa-chevron-up' : 'fa-chevron-down'} text-[9px] opacity-70`}></i>
      </button>
      {open && (
        <div className="mt-1 rounded border border-warning bg-surface-muted p-2 text-[11px] text-fg-muted space-y-2 font-mono">
          {warning.description && (
            <div className="text-warning-fg font-sans">{warning.description}</div>
          )}
          {warning.snippet && (
            <div>
              <div className="text-fg-subtle text-[10px] uppercase tracking-wide mb-0.5 font-sans">snippet</div>
              <pre className="whitespace-pre-wrap break-words text-warning-fg">{warning.snippet}</pre>
            </div>
          )}
          {hasRaw && (
            <div>
              <div className="text-fg-subtle text-[10px] uppercase tracking-wide mb-0.5 font-sans">raw content ({rawContent.length} chars)</div>
              <pre className="whitespace-pre-wrap break-words max-h-64 overflow-auto text-fg">{rawContent}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
