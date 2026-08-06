import ToolResultBlock from './ToolResultBlock'

// A tool call is glance-level context, not a document. Everything that can be
// on one line is: name + arguments on the first row, the result on the second.
//
// Argument values are summarized, not previewed. A write tool carries an
// entire file body here — a 40-char prefix of a story is noise, so anything
// long is reported as a size instead. The payload is available in the debug
// overlay when it's actually wanted.
const ARG_INLINE_MAX = 48
const ARG_SUMMARIZE_OVER = 160

function formatArg(value) {
  if (value == null) return String(value)
  if (typeof value === 'string') {
    if (value.length > ARG_SUMMARIZE_OVER) return `${value.length.toLocaleString()} chars`
    const flat = value.replace(/\s+/g, ' ').trim()
    return flat.length > ARG_INLINE_MAX ? `${flat.slice(0, ARG_INLINE_MAX)}…` : flat
  }
  if (typeof value === 'object') {
    const s = JSON.stringify(value)
    return s.length > ARG_INLINE_MAX ? `${s.slice(0, ARG_INLINE_MAX)}…` : s
  }
  return String(value)
}

export default function ToolCallBubble({ name, args, result, hasResult, running, progress }) {
  const entries = args && typeof args === 'object' ? Object.entries(args) : []
  const done = hasResult ?? result != null
  return (
    <div className="rounded px-2 py-1 text-xs border bg-surface-muted border-border">
      {/* Name and arguments share one row; the row truncates rather than wraps. */}
      <div className="flex items-baseline gap-2 min-w-0">
        <span className={`flex-shrink-0 ${done ? 'text-success-fg' : 'text-warning-fg'}`}>
          <i className={`fa-solid ${done ? 'fa-check' : 'fa-wrench fa-fade'} mr-1.5`}></i>
          <span className="font-mono">{name}</span>
        </span>
        {entries.length > 0 && (
          <span className="font-mono text-fg-subtle truncate min-w-0">
            {entries.map(([k, v]) => `${k}=${formatArg(v)}`).join('  ')}
          </span>
        )}
        {running && !done && (
          <span className="flex-shrink-0 ml-auto text-[10px] uppercase tracking-wide text-fg-subtle">running…</span>
        )}
      </div>

      {/* Live progress streamed by the MCP server while the tool runs. */}
      {!done && progress && progress.length > 0 && (
        <div className="mt-0.5 text-fg-muted font-mono text-[10px] whitespace-pre-wrap break-words max-h-24 overflow-y-auto">
          {progress.join('')}
        </div>
      )}

      {done && (
        <div className="mt-0.5">
          <ToolResultBlock text={result} />
        </div>
      )}
    </div>
  )
}
