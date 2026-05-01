import { useMemo } from 'react'
import useServiceMetrics from '../hooks/useServiceMetrics'
import TokenSparkline from './TokenSparkline'
import RequestStrip from './RequestStrip'
import GaugesRow from './GaugesRow'
import SpecDecodeBar from './SpecDecodeBar'
import { getValue, timeAgo } from '../utils'

export default function MetricsPanel({ serviceName, enabled }) {
  const { metrics, history, loading, error, lastScraped } = useServiceMetrics({ serviceName, enabled })

  const latest = history.length > 0 ? history[history.length - 1] : {}

  const specPerPos = useMemo(() => {
    const raw = metrics['vllm:spec_decode_num_accepted_tokens_per_pos_total']
    if (!raw || typeof raw !== 'object') return null
    const entries = Object.entries(raw)
    if (entries.length === 0) return null
    return raw
  }, [metrics])

  if (!enabled) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-2 h-2 rounded-full bg-gray-600" />
          <h3 className="text-base font-semibold text-gray-100">Live Metrics</h3>
          <span className="text-gray-500 text-sm">(disabled)</span>
        </div>
        <p className="text-gray-400 text-sm">
          Metrics are only available for running vLLM services. Start the service to see live metrics.
        </p>
      </div>
    )
  }

  const hasHistory = history.length > 0

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-5">
      <div className="flex items-center gap-3 mb-5">
        <div className={`w-2 h-2 rounded-full ${error ? 'bg-red-500' : 'bg-green-500 animate-pulse'}`} />
        <h3 className="text-base font-semibold text-gray-100">Live Metrics</h3>
        <span className="text-gray-500 text-xs">{loading ? 'Initial fetch...' : timeAgo(lastScraped)}</span>
        {error && <span className="text-red-400 text-xs ml-auto">{error}</span>}
      </div>

      {!hasHistory && !loading && !error ? (
        <div className="flex flex-col items-center justify-center py-12">
          <i className="fa-solid fa-chart-line text-3xl text-gray-600 mb-3" />
          <p className="text-gray-400 text-sm mb-1">No metrics available</p>
          <p className="text-gray-500 text-xs">The vLLM prometheus endpoint returned no data or is unreachable.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="flex flex-col gap-4">
            <RequestStrip
              running={latest.running}
              waiting={latest.waiting}
              preemptRate={latest.preemptRate}
            />
            <TokenSparkline history={history} />
          </div>
          <div className="flex flex-col gap-4">
            <GaugesRow
              kvCache={getValue(metrics, 'vllm:kv_cache_usage_perc')}
              prefixHitRatio={latest.prefixHitRatio}
              specAcceptRatio={latest.specAcceptRatio}
            />
            {specPerPos && <SpecDecodeBar specPerPos={specPerPos} />}
          </div>
        </div>
      )}
    </div>
  )
}
