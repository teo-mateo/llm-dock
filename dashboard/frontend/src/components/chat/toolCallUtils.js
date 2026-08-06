// Argument values are a glance-level summary, not the payload — a write tool
// puts an entire file body here, and the row is single-line/truncated anyway.
const ARG_VALUE_MAX = 60

export function formatArgValue(v) {
  if (v == null) return String(v)
  if (typeof v === 'string') {
    const flat = v.replace(/\s+/g, ' ').trim()
    return flat.length > ARG_VALUE_MAX ? flat.slice(0, ARG_VALUE_MAX) + '…' : flat
  }
  if (typeof v === 'object') {
    const s = JSON.stringify(v)
    return s.length > ARG_VALUE_MAX ? s.slice(0, ARG_VALUE_MAX) + '…' : s
  }
  return String(v)
}
