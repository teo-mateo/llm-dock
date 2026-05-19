import { useState } from 'react'

const PREVIEW_CHARS = 160

export default function ToolResultBlock({ text }) {
  const [open, setOpen] = useState(false)
  const s = typeof text === 'string' ? text : String(text ?? '')
  const long = s.length > PREVIEW_CHARS
  const preview = long ? s.slice(0, PREVIEW_CHARS).replace(/\s+$/, '') + '…' : s
  return (
    <div className="text-fg-muted inline">
      <span className="text-success-fg mr-1">→</span>
      {open || !long ? (
        <pre className="font-mono whitespace-pre-wrap break-words bg-surface-muted border border-border rounded px-2 py-1 mt-1 max-h-80 overflow-auto text-[11px] text-fg-muted">{s}</pre>
      ) : (
        <span className="font-mono text-fg-muted">{preview}</span>
      )}
      {long && (
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="ml-2 text-[10px] uppercase tracking-wide text-fg-subtle hover:text-fg-muted"
        >
          {open ? 'collapse' : `show all (${s.length.toLocaleString()} chars)`}
        </button>
      )}
    </div>
  )
}
