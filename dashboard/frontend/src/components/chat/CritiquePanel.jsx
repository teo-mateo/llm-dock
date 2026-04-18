import { useState } from 'react'
import CritiqueOverlay from './CritiqueOverlay'

export default function CritiquePanel({ messageId, originalContent, critique, loading, onCritique, onClose, onInsertAnnotation }) {
  const [instructions, setInstructions] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    onCritique(messageId, instructions)
  }

  return (
    <div className="w-96 border-l border-gray-700 flex flex-col bg-gray-850 flex-shrink-0 overflow-hidden"
         style={{ backgroundColor: '#1a1d23' }}>
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          <i className="fa-solid fa-magnifying-glass text-yellow-400"></i>
          <span>Critique</span>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
          <i className="fa-solid fa-xmark"></i>
        </button>
      </div>

      {/* Instructions input */}
      <form onSubmit={handleSubmit} className="px-4 py-3 border-b border-gray-700">
        <label className="text-xs text-gray-400 mb-1.5 block">Extra instructions for the critic</label>
        <textarea
          value={instructions}
          onChange={e => setInstructions(e.target.value)}
          placeholder="e.g. Focus on factual accuracy, check the math, verify the code..."
          rows={2}
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-xs text-gray-200 resize-none focus:outline-none focus:border-yellow-500/50 placeholder-gray-600"
        />
        <button
          type="submit"
          disabled={loading}
          className="mt-2 w-full px-3 py-1.5 bg-yellow-600/20 text-yellow-400 border border-yellow-600/30 rounded text-xs font-medium hover:bg-yellow-600/30 disabled:opacity-50 transition-colors"
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
          <div className="text-center text-gray-500 py-8">
            <i className="fa-solid fa-spinner fa-spin text-xl mb-3 block"></i>
            <p className="text-xs">Sidekick is reviewing...</p>
          </div>
        )}

        {critique && (
          <CritiqueOverlay critique={critique} originalContent={originalContent} onInsertAnnotation={onInsertAnnotation} />
        )}

        {!critique && !loading && (
          <div className="text-center text-gray-600 py-8 text-xs">
            Click "Run Critique" to have the sidekick review this response
          </div>
        )}
      </div>
    </div>
  )
}
