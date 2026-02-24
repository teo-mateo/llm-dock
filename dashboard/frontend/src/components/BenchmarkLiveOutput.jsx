import { useState, useEffect } from 'react'

const STATUS_CONFIG = {
  idle: { text: 'Idle', className: 'bg-gray-700 text-gray-400' },
  running: { text: 'Running', className: 'bg-yellow-900 text-yellow-300' },
  completed: { text: 'Completed', className: 'bg-green-900 text-green-300' },
  failed: { text: 'Failed', className: 'bg-red-900 text-red-300' },
  cancelled: { text: 'Cancelled', className: 'bg-red-900 text-red-300' },
}

export default function BenchmarkLiveOutput({ output, outputClass, runStatus }) {
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (runStatus === 'running') setExpanded(true)
  }, [runStatus])

  const status = STATUS_CONFIG[runStatus] || STATUS_CONFIG.idle

  return (
    <div className="bg-gray-800 rounded-lg p-5 mb-6">
      <div
        className="flex items-center justify-between cursor-pointer select-none"
        onClick={() => setExpanded(e => !e)}
      >
        <h2 className="text-lg font-semibold">
          <i className={`fa-solid fa-chevron-down mr-1.5 text-gray-500 text-xs transition-transform ${
            !expanded ? 'rotate-[-90deg]' : ''
          }`}></i>
          <i className="fa-solid fa-terminal mr-2 text-gray-400"></i>Live Output
        </h2>
        <span className={`px-2 py-0.5 rounded text-xs font-semibold ${status.className}`}>
          {status.text}
        </span>
      </div>
      {expanded && (
        <div className="mt-3">
          <div className={`font-mono text-sm leading-relaxed whitespace-pre-wrap break-all bg-gray-950 rounded p-4 h-64 overflow-y-auto ${outputClass}`}>
            {output}
          </div>
        </div>
      )}
    </div>
  )
}
