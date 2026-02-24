const STATUS_ICONS = {
  completed: <span className="text-green-400"><i className="fa-solid fa-check"></i> Completed</span>,
  failed: <span className="text-red-400"><i className="fa-solid fa-xmark"></i> Failed</span>,
  running: <span className="text-yellow-400"><i className="fa-solid fa-spinner fa-spin"></i> Running</span>,
  pending: <span className="text-gray-400"><i className="fa-solid fa-clock"></i> Pending</span>,
  cancelled: <span className="text-gray-400"><i className="fa-solid fa-ban"></i> Cancelled</span>,
}

export default function BenchmarkHistory({ history, onRerun, onApply, onDelete }) {
  return (
    <div className="bg-gray-800 rounded-lg p-5">
      <h2 className="text-lg font-semibold mb-3">
        <i className="fa-solid fa-clock-rotate-left mr-2 text-gray-400"></i>History
      </h2>

      {history.length === 0 ? (
        <p className="text-gray-500 text-sm mt-3">No benchmark history yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left border-b border-gray-700">
                <th className="pb-2 pr-3">Date</th>
                <th className="pb-2 pr-3">PP t/s</th>
                <th className="pb-2 pr-3">TG t/s</th>
                <th className="pb-2 pr-3">Key Params</th>
                <th className="pb-2 pr-3">Status</th>
                <th className="pb-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {history.map(row => {
                const allParams = Object.entries(row.params || {})
                  .map(([flag, val]) => val ? `${flag} ${val}` : flag)
                  .join('  ')

                return (
                  <tr key={row.id} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                    <td className="py-2.5 pr-3 text-gray-300 text-xs whitespace-nowrap">{row.date}</td>
                    <td className={`py-2.5 pr-3 font-mono ${row.pp_ts ? 'text-white' : 'text-gray-500'}`}>
                      {row.pp_ts ? row.pp_ts.toFixed(1) : '\u2014'}
                    </td>
                    <td className={`py-2.5 pr-3 font-mono ${row.tg_ts ? 'text-white' : 'text-gray-500'}`}>
                      {row.tg_ts ? row.tg_ts.toFixed(1) : '\u2014'}
                    </td>
                    <td className="py-2.5 pr-3 text-gray-400 text-xs font-mono">{allParams}</td>
                    <td className="py-2.5 pr-3 text-xs">
                      {STATUS_ICONS[row.status] || <span className="text-gray-400">{row.status}</span>}
                    </td>
                    <td className="py-2.5">
                      <div className="flex gap-1">
                        <button
                          onClick={() => onRerun(row.id)}
                          className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded cursor-pointer"
                          title="Re-run with these params"
                        >
                          <i className="fa-solid fa-rotate-right"></i> Re-run
                        </button>
                        {row.status === 'completed' && (
                          <button
                            onClick={() => onApply(row.id)}
                            className="text-xs bg-blue-700 hover:bg-blue-600 px-2 py-1 rounded cursor-pointer"
                            title="Apply config to service"
                          >
                            <i className="fa-solid fa-upload"></i> Apply
                          </button>
                        )}
                        <button
                          onClick={() => onDelete(row.id)}
                          className="text-xs bg-red-700 hover:bg-red-600 px-2 py-1 rounded cursor-pointer"
                          title="Delete"
                        >
                          <i className="fa-solid fa-trash"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
