import { BENCHMARK_ONLY_FLAGS } from '../hooks/useBenchmark'

export default function BenchmarkParamsPanel({
  params,
  isRunning,
  commandPreview,
  onFlagChange,
  onValueChange,
  onRemove,
  onReset,
  onRun,
}) {
  return (
    <div>
      {/* Parameters */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 mb-4">
        <div className="px-5 py-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-gray-200">
            <i className="fa-solid fa-sliders mr-2 text-gray-400"></i>Parameters
          </h2>
        </div>
        <div className="p-5">
        <div className="flex flex-col gap-2 mb-3">
          {params.map(p => {
            const isBench = BENCHMARK_ONLY_FLAGS.has(p.flag)
            return (
              <div
                key={p.id}
                className={`flex gap-2 items-center border-l-2 rounded-r pl-1 ${
                  isBench ? 'border-orange-500/50' : 'border-transparent'
                }`}
              >
                <input
                  type="text"
                  value={p.flag}
                  placeholder="-flag"
                  onChange={e => onFlagChange(p.id, e.target.value)}
                  className={`bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm w-40 font-mono focus:outline-none focus:border-blue-500 ${
                    isBench ? 'text-orange-400' : ''
                  }`}
                />
                <input
                  type="text"
                  value={p.value}
                  placeholder="value (empty = boolean flag)"
                  onChange={e => onValueChange(p.id, e.target.value)}
                  className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm flex-1 font-mono focus:outline-none focus:border-blue-500"
                />
                {isBench && (
                  <span className="text-[9px] uppercase tracking-wide font-semibold bg-orange-500/15 text-orange-400 px-1.5 py-0.5 rounded whitespace-nowrap">
                    bench
                  </span>
                )}
                <button
                  onClick={() => onRemove(p.id)}
                  className={`text-red-400 hover:text-red-300 px-2 py-1 cursor-pointer ${
                    p.isEmpty ? 'invisible' : ''
                  }`}
                  title="Remove"
                >
                  <i className="fa-solid fa-xmark"></i>
                </button>
              </div>
            )
          })}
        </div>
        <div className="flex gap-2">
          <button
            onClick={onReset}
            className="text-sm bg-gray-700 hover:bg-gray-600 px-3 py-1.5 rounded cursor-pointer"
          >
            <i className="fa-solid fa-rotate-left mr-1"></i> Reset
          </button>
        </div>
        </div>
      </div>

      {/* Command Preview */}
      <div className="bg-gray-800 rounded-lg p-5 mb-4">
        <h2 className="text-sm font-semibold text-gray-400 mb-2">Command Preview</h2>
        <div className="font-mono text-sm text-green-400 bg-gray-950 rounded p-3 break-all">
          {commandPreview}
        </div>
      </div>

      {/* Run Button */}
      <div className="flex gap-3">
        <button
          onClick={onRun}
          disabled={isRunning}
          className={`px-5 py-2.5 rounded font-semibold text-sm cursor-pointer ${
            isRunning
              ? 'bg-gray-600 !cursor-not-allowed'
              : 'bg-green-600 hover:bg-green-700'
          }`}
        >
          {isRunning ? (
            <>
              <i className="fa-solid fa-spinner fa-spin mr-1"></i> Running...
            </>
          ) : (
            <>
              <i className="fa-solid fa-play mr-1"></i> Run Benchmark
            </>
          )}
        </button>
      </div>
    </div>
  )
}
