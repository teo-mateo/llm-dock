const TONES = {
  neutral: 'border-border text-fg-muted',
  success: 'border-success bg-success-subtle text-success-fg',
  warning: 'border-warning bg-warning-subtle text-warning-fg',
  danger: 'border-danger bg-danger-subtle text-danger-fg',
}

export default function ToolChip({ tone = 'neutral', title, children }) {
  return (
    <span title={title} className={`rounded border px-1.5 font-mono text-xs ${TONES[tone]}`}>
      {children}
    </span>
  )
}
