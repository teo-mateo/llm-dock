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
        className="inline-flex items-center gap-1.5 rounded border border-yellow-600/40 bg-yellow-900/20 px-2 py-0.5 text-[11px] text-yellow-300 hover:bg-yellow-900/40"
        title="Click to inspect"
      >
        <i className={`fa-solid fa-triangle-exclamation`}></i>
        <span>{label}</span>
        <i className={`fa-solid ${open ? 'fa-chevron-up' : 'fa-chevron-down'} text-[9px] opacity-70`}></i>
      </button>
      {open && (
        <div className="mt-1 rounded border border-yellow-600/30 bg-gray-900/60 p-2 text-[11px] text-gray-300 space-y-2 font-mono">
          {warning.description && (
            <div className="text-yellow-300/90 font-sans">{warning.description}</div>
          )}
          {warning.snippet && (
            <div>
              <div className="text-gray-500 text-[10px] uppercase tracking-wide mb-0.5 font-sans">snippet</div>
              <pre className="whitespace-pre-wrap break-words text-yellow-100/90">{warning.snippet}</pre>
            </div>
          )}
          {hasRaw && (
            <div>
              <div className="text-gray-500 text-[10px] uppercase tracking-wide mb-0.5 font-sans">raw content ({rawContent.length} chars)</div>
              <pre className="whitespace-pre-wrap break-words max-h-64 overflow-auto text-gray-200">{rawContent}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
