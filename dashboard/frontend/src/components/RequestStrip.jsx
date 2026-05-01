export default function RequestStrip({ running, waiting, preemptRate }) {
  const fmt = (val) => val !== undefined && val != null ? val : '—'

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <h3 className="text-sm font-medium text-gray-400 mb-3">Requests</h3>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <span className="flex items-center gap-1.5 text-gray-300">
          <i className="fa-solid fa-bolt text-yellow-400 text-xs" />
          Running: <span className="font-mono font-semibold">{fmt(running)}</span>
        </span>
        <span className="text-gray-600">|</span>
        <span className="flex items-center gap-1.5 text-gray-300">
          <i className="fa-solid fa-clock text-blue-400 text-xs" />
          Waiting: <span className="font-mono font-semibold">{fmt(waiting)}</span>
        </span>
        <span className="text-gray-600">|</span>
        <span className="flex items-center gap-1.5 text-gray-300">
          <i className="fa-solid fa-arrows-rotate text-red-400 text-xs" />
          Preempt: <span className="font-mono font-semibold">{typeof preemptRate === 'number' ? preemptRate.toFixed(1) : fmt(preemptRate)}</span>
          {typeof preemptRate === 'number' && <span className="text-gray-500 text-xs">/s</span>}
        </span>
      </div>
    </div>
  )
}
