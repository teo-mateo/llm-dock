import { useState } from 'react'

const PREVIEW_CHARS = 160

export default function ToolResultBlock({ text }) {
  const [open, setOpen] = useState(false)
  const s = typeof text === 'string' ? text : String(text ?? '')
  const long = s.length > PREVIEW_CHARS
  const preview = long ? s.slice(0, PREVIEW_CHARS).replace(/\s+$/, '') + '…' : s
  return (
    <div className="text-fg-muted">
      <span className="text-success-fg mr-1">→</span>
      {/* Stay on the arrow's line unless the result is genuinely long AND
          expanded — a <pre> is block-level, so using it for a short result
          like "Created joke2.txt (71 bytes)" pushed the text onto its own
          line for no reason. */}
      {long && open ? (
        <pre className="font-mono whitespace-pre-wrap break-words bg-surface-muted border border-border rounded px-2 py-1 mt-1 max-h-80 overflow-auto text-[11px] text-fg-muted">{s}</pre>
      ) : (
        <span className="font-mono text-fg-muted whitespace-pre-wrap break-words">{long ? preview : s}</span>
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
