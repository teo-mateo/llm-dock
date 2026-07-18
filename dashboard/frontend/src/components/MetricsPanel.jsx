import { useMemo } from 'react'
import useServiceMetrics from '../hooks/useServiceMetrics'
import TokenSparkline from './TokenSparkline'
import RequestStrip from './RequestStrip'
import GaugesRow from './GaugesRow'
import SpecDecodeBar from './SpecDecodeBar'
import { getValue, totalValue, timeAgo } from '../utils'

function fmt(n) {
  if (n == null) return '—'
  return n.toLocaleString()
}

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

  const promptTotal = totalValue(metrics, 'vllm:prompt_tokens_total')
  const genTotal = totalValue(metrics, 'vllm:generation_tokens_total')
  const showCumulative = promptTotal != null || genTotal != null

  if (!enabled) {
    return (
      <div className="bg-surface rounded-lg border border-border p-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-2 h-2 rounded-full bg-surface-muted" />
          <h3 className="text-base font-semibold text-fg">Live Metrics</h3>
          <span className="text-fg-subtle text-sm">(disabled)</span>
        </div>
        <p className="text-fg-muted text-sm">
          Metrics are only available for running services. Start the service to see live metrics.
        </p>
      </div>
    )
  }

  const hasHistory = history.length > 0

  return (
    <div className="bg-surface rounded-lg border border-border p-5">
      <div className="flex items-center gap-3 mb-5">
        <div className={`w-2 h-2 rounded-full ${error ? 'bg-danger' : 'bg-success animate-pulse'}`} />
        <h3 className="text-base font-semibold text-fg">Live Metrics</h3>
        <span className="text-fg-subtle text-xs">{loading ? 'Initial fetch...' : timeAgo(lastScraped)}</span>
        {error && <span className="text-danger-fg text-xs ml-auto">{error}</span>}
      </div>

      {showCumulative && (
        <div className="flex items-center gap-6 mb-4 px-1 text-xs font-mono">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-accent" />
            <span className="text-fg-muted">Prompt:</span>
            <span className="text-fg font-semibold">{fmt(promptTotal)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-success" />
            <span className="text-fg-muted">Gen:</span>
            <span className="text-fg font-semibold">{fmt(genTotal)}</span>
          </div>
          <div className="flex items-center gap-1.5 ml-auto">
            <span className="text-fg-subtle">Total:</span>
            <span className="text-fg font-semibold">{fmt((promptTotal || 0) + (genTotal || 0))}</span>
          </div>
        </div>
      )}

      {!hasHistory && !loading && !error ? (
        <div className="flex flex-col items-center justify-center py-12">
          <i className="fa-solid fa-chart-line text-3xl text-fg-faint mb-3" />
          <p className="text-fg-muted text-sm mb-1">No metrics available</p>
          <p className="text-fg-subtle text-xs">The prometheus endpoint returned no data or is unreachable.</p>
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
