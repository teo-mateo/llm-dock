export default function PiNotice({ change, text }) {
  if (change) {
    return (
      <div className="flex justify-center">
        <div className="flex max-w-full flex-wrap items-center justify-center gap-x-2 gap-y-1 rounded-xl border border-border bg-elevated px-3 py-2 text-xs">
          <span className="font-semibold text-fg-subtle">{change.label}</span>
          <span className="rounded-md bg-app px-1.5 py-0.5 font-mono text-fg-muted break-all">
            {change.from}
          </span>
          <span aria-hidden="true" className="text-accent">→</span>
          <span className="rounded-md bg-app px-1.5 py-0.5 font-mono text-fg break-all">
            {change.to}
          </span>
        </div>
      </div>
    )
  }
  if (text) {
    return (
      <div className="flex justify-center">
        <p className="rounded-full border border-border bg-elevated px-3 py-1 text-xs text-fg-muted">
          {text}
        </p>
      </div>
    )
  }
  return null
}
