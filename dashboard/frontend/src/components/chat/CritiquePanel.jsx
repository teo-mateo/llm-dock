import { useState } from 'react'
import CritiqueOverlay from './CritiqueOverlay'

export default function CritiquePanel({ messageId, critique, loading, onCritique, onClose, onInsertAnnotation }) {
  const [instructions, setInstructions] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    onCritique(messageId, instructions)
  }

  return (
    <div className="w-96 border-l border-border flex flex-col bg-elevated flex-shrink-0 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          <i className="fa-solid fa-magnifying-glass text-warning-fg"></i>
          <span>Critique</span>
        </div>
        <button onClick={onClose} className="text-fg-subtle hover:text-fg-muted">
          <i className="fa-solid fa-xmark"></i>
        </button>
      </div>

      {/* Instructions input */}
      <form onSubmit={handleSubmit} className="px-4 py-3 border-b border-border">
        <label className="text-xs text-fg-muted mb-1.5 block">Extra instructions for the critic</label>
        <textarea
          value={instructions}
          onChange={e => setInstructions(e.target.value)}
          placeholder="e.g. Focus on factual accuracy, check the math, verify the code..."
          rows={2}
          className="w-full bg-surface border border-border rounded px-3 py-2 text-xs text-fg resize-none focus:outline-none focus:border-warning placeholder-fg-faint"
        />
        <button
          type="submit"
          disabled={loading}
          className="mt-2 w-full px-3 py-1.5 bg-warning-subtle text-warning-fg border border-warning rounded text-xs font-medium hover:bg-warning-subtle disabled:opacity-50 transition-colors"
        >
          {loading ? (
            <><i className="fa-solid fa-spinner fa-spin mr-1.5"></i>Critiquing...</>
          ) : critique ? (
            <><i className="fa-solid fa-rotate mr-1.5"></i>Re-critique</>
          ) : (
            <><i className="fa-solid fa-magnifying-glass mr-1.5"></i>Run Critique</>
          )}
        </button>
      </form>

      {/* Results */}
      <div className="flex-1 overflow-auto px-4 py-3">
        {loading && !critique && (
          <div className="text-center text-fg-subtle py-8">
            <i className="fa-solid fa-spinner fa-spin text-xl mb-3 block"></i>
            <p className="text-xs">Critic is reviewing...</p>
          </div>
        )}

        {critique && (
          <CritiqueOverlay critique={critique} onInsertAnnotation={onInsertAnnotation} />
        )}

        {!critique && !loading && (
          <div className="text-center text-fg-faint py-8 text-xs">
            Click "Run Critique" to have the critic review this response
          </div>
        )}
      </div>
    </div>
  )
}
