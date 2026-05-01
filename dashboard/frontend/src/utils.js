export function getValue(metrics, metricName) {
  const obj = metrics[metricName]
  if (!obj || typeof obj !== 'object') return undefined
  const keys = Object.keys(obj)
  if (keys.length === 0) return undefined
  return obj[keys[0]]
}

export function timeAgo(iso) {
  if (!iso) return '—'
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  return `${Math.round(diff / 3600)}h ago`
}