import { useState } from 'react'

const PREVIEW_CHARS = 160

export default function ToolResultBlock({ text }) {
  const [open, setOpen] = useState(false)
  const s = typeof text === 'string' ? text : String(text ?? '')
  const long = s.length > PREVIEW_CHARS
  const preview = long ? s.slice(0, PREVIEW_CHARS).replace(/\s+$/, '') + '…' : s
  return (
    <div className="text-gray-300 inline">
      <span className="text-green-400 mr-1">→</span>
      {open || !long ? (
        <pre className="font-mono whitespace-pre-wrap break-words bg-gray-950/60 border border-gray-800 rounded px-2 py-1 mt-1 max-h-80 overflow-auto text-[11px] text-gray-300">{s}</pre>
      ) : (
        <span className="font-mono text-gray-400">{preview}</span>
      )}
      {long && (
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="ml-2 text-[10px] uppercase tracking-wide text-gray-500 hover:text-gray-300"
        >
          {open ? 'collapse' : `show all (${s.length.toLocaleString()} chars)`}
        </button>
      )}
    </div>
  )
}
