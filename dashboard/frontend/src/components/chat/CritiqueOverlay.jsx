const VERDICT_STYLES = {
  pass: 'text-green-400 bg-green-500/10 border-green-500/30',
  minor_issues: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
  major_issues: 'text-red-400 bg-red-500/10 border-red-500/30',
}

const SEVERITY_COLORS = {
  error: { badge: 'bg-red-500/20 text-red-300', border: 'border-red-500/30', icon: 'text-red-400' },
  warning: { badge: 'bg-yellow-500/20 text-yellow-300', border: 'border-yellow-500/30', icon: 'text-yellow-400' },
  info: { badge: 'bg-blue-500/20 text-blue-300', border: 'border-blue-500/30', icon: 'text-blue-400' },
}

function AnnotationCard({ annotation, index, onInsert }) {
  const severity = annotation.severity || 'info'
  const colors = SEVERITY_COLORS[severity] || SEVERITY_COLORS.info

  return (
    <div className={`rounded border ${colors.border} bg-gray-900/50 overflow-hidden`}>
      {/* Header */}
      <div className="px-3 py-1.5 flex items-center gap-2 border-b border-gray-800/50">
        <span className={`text-[10px] font-bold uppercase ${colors.icon}`}>
          {severity === 'error' ? '!' : severity === 'warning' ? '?' : 'i'}
        </span>
        <span className="text-[10px] text-gray-400 uppercase tracking-wide">{annotation.issue_type}</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${colors.badge}`}>{severity}</span>
      </div>

      {/* Quoted span */}
      {annotation.span_text && (
        <div className="px-3 py-2 border-b border-gray-800/50">
          <div className="text-[10px] text-gray-500 mb-1">Referenced text:</div>
          <div className={`text-xs text-gray-300 italic border-l-2 ${colors.border} pl-2`}>
            "{annotation.span_text}"
          </div>
        </div>
      )}

      {/* Comment + Insert button */}
      <div className="px-3 py-2 flex items-start gap-2">
        <p className="text-xs text-gray-300 leading-relaxed flex-1">{annotation.comment}</p>
        <button
          onClick={() => onInsert(annotation)}
          className="flex-shrink-0 text-[10px] px-2 py-1 rounded bg-blue-600/20 text-blue-400 border border-blue-600/30 hover:bg-blue-600/30 transition-colors"
          title="Insert into next message"
        >
          <i className="fa-solid fa-arrow-right-to-bracket mr-1"></i>Insert
        </button>
      </div>
    </div>
  )
}

export default function CritiqueOverlay({ critique, originalContent, onInsertAnnotation }) {
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
          <div className="text-[10px] text-gray-500 uppercase tracking-wide">
            {annotations.length} issue{annotations.length !== 1 ? 's' : ''} found
          </div>
          {annotations.map((ann, i) => (
            <AnnotationCard key={i} annotation={ann} index={i} onInsert={onInsertAnnotation} />
          ))}
        </div>
      )}

      {annotations.length === 0 && verdict === 'pass' && (
        <div className="text-xs text-gray-500 text-center py-4">
          <i className="fa-solid fa-check-circle text-green-500 text-lg mb-2 block"></i>
          No issues found
        </div>
      )}
    </div>
  )
}
