export function getValue(metrics, metricName) {
  const obj = metrics[metricName]
  if (!obj || typeof obj !== 'object') return undefined
  const keys = Object.keys(obj)
  if (keys.length === 0) return undefined
  return obj[keys[0]]
}

export function totalValue(metrics, metricName) {
  const obj = metrics[metricName]
  if (!obj || typeof obj !== 'object') return null
  const vals = Object.values(obj).filter(v => typeof v === 'number')
  if (vals.length === 0) return null
  return vals.reduce((a, b) => a + b, 0)
}