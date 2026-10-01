import { getValue, totalValue } from '../utils'

function format(value, digits = 0) {
  return value == null || !Number.isFinite(value) ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: digits })
}

function Stat({ label, value }) {
  return <div className="flex justify-between gap-4 text-xs">
    <dt className="text-fg-muted">{label}</dt>
    <dd className="font-mono text-fg">{value}</dd>
  </div>
}

export default function SglangMetricsDetails({ metrics }) {
  const value = name => getValue(metrics, `sglang:${name}`)
  const pool = prefix => ['used', 'evictable', 'available'].map(kind => value(`${prefix}_${kind}_tokens`))
  const states = pool('mamba')
  const stateCapacity = states.every(v => v != null) ? states.reduce((a, b) => a + b, 0) : undefined
  const groups = [
    ['KV tokens', [
      ['Capacity', value('max_total_num_tokens')],
      ['Active', value('kv_used_tokens')],
      ['Prefix cached', value('kv_evictable_tokens')],
      ['Free', value('kv_available_tokens')],
    ]],
    ['Mamba state slots', [
      ['Capacity', stateCapacity], ['Active', states[0]],
      ['Prefix cached', states[1]], ['Free', states[2]],
    ]],
    ['Host KV cache', [
      ['Used tokens', value('hicache_host_used_tokens')],
      ['Capacity tokens', value('hicache_host_total_tokens')],
    ]],
    ['Engine', [
      ['Target weights (GB)', value('weight_memory_usage_gb'), 2],
      ['KV cache (GB)', value('kv_cache_memory_usage_gb'), 2],
      ['CUDA graphs (GB)', totalValue(metrics, 'sglang:graph_memory_usage_gb'), 2],
      ['Spec tokens per verify', value('spec_accept_length'), 2],
    ]],
  ]
  return <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
    {groups.map(([title, rows]) => <section key={title} className="bg-surface rounded-lg border border-border p-4">
      <h3 className="text-sm font-medium text-fg-muted mb-3">{title}</h3>
      <dl className="flex flex-col gap-2">
        {rows.map(([label, number, digits]) => <Stat key={label} label={label} value={format(number, digits)} />)}
      </dl>
    </section>)}
  </div>
}
