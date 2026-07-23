const VERDICT_STYLES = {
  pass: 'text-success-fg bg-success-subtle border-success',
  minor_issues: 'text-warning-fg bg-warning-subtle border-warning',
  major_issues: 'text-danger-fg bg-danger-subtle border-danger',
}

const SEVERITY_COLORS = {
  error: { badge: 'bg-danger-subtle text-danger-fg', border: 'border-danger', icon: 'text-danger-fg' },
  warning: { badge: 'bg-warning-subtle text-warning-fg', border: 'border-warning', icon: 'text-warning-fg' },
  info: { badge: 'bg-accent-subtle text-accent-fg', border: 'border-accent', icon: 'text-accent-fg' },
}

function AnnotationCard({ annotation, onInsert }) {
  const severity = annotation.severity || 'info'
  const colors = SEVERITY_COLORS[severity] || SEVERITY_COLORS.info

  return (
    <div className={`rounded border ${colors.border} bg-surface-muted overflow-hidden`}>
      {/* Header */}
      <div className="px-3 py-1.5 flex items-center gap-2 border-b border-border-subtle">
        <span className={`text-[10px] font-bold uppercase ${colors.icon}`}>
          {severity === 'error' ? '!' : severity === 'warning' ? '?' : 'i'}
        </span>
        <span className="text-[10px] text-fg-muted uppercase tracking-wide">{annotation.issue_type}</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${colors.badge}`}>{severity}</span>
      </div>

      {/* Quoted span */}
      {annotation.span_text && (
        <div className="px-3 py-2 border-b border-border-subtle">
          <div className="text-[10px] text-fg-subtle mb-1">Referenced text:</div>
          <div className={`text-xs text-fg-muted italic border-l-2 ${colors.border} pl-2`}>
            "{annotation.span_text}"
          </div>
        </div>
      )}

      {/* Comment + Insert button */}
      <div className="px-3 py-2 flex items-start gap-2">
        <p className="text-xs text-fg-muted leading-relaxed flex-1">{annotation.comment}</p>
        <button
          onClick={() => onInsert(annotation)}
          className="flex-shrink-0 text-[10px] px-2 py-1 rounded bg-accent-subtle text-accent-fg border border-accent hover:bg-accent-subtle transition-colors"
          title="Insert into next message"
        >
          <i className="fa-solid fa-arrow-right-to-bracket mr-1"></i>Insert
        </button>
      </div>
    </div>
  )
}

export default function CritiqueOverlay({ critique, onInsertAnnotation }) {
  if (!critique) return null

  const verdict = critique.verdict || 'pass'
  const verdictStyle = VERDICT_STYLES[verdict] || ''
  const annotations = critique.annotations || []

  return (
    <div className="space-y-3">
      {/* Verdict banner */}
      <div className={`text-xs px-3 py-2 rounded border ${verdictStyle}`}>
        <span className="font-medium capitalize">{verdict.replace('_', ' ')}</span>
        {critique.summary && (
          <p className="mt-1 opacity-80">{critique.summary}</p>
        )}
      </div>

      {/* Annotation cards */}
      {annotations.length > 0 && (
        <div className="space-y-2">
          <div className="text-[10px] text-fg-subtle uppercase tracking-wide">
            {annotations.length} issue{annotations.length !== 1 ? 's' : ''} found
          </div>
          {annotations.map((ann, i) => (
            <AnnotationCard key={i} annotation={ann} index={i} onInsert={onInsertAnnotation} />
          ))}
        </div>
      )}

      {annotations.length === 0 && verdict === 'pass' && (
        <div className="text-xs text-fg-subtle text-center py-4">
          <i className="fa-solid fa-check-circle text-success-fg text-lg mb-2 block"></i>
          No issues found
        </div>
      )}
    </div>
  )
}
