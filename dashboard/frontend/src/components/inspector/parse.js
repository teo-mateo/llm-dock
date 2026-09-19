// Pure helpers for the inspector viewer. A component file that exports a
// non-component breaks Fast refresh (react-refresh/only-export-components),
// so everything shared across the inspector components lives here.

export function relativeTime(iso) {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const diff = Date.now() - then
  if (diff < 15000) return 'just now'
  const minutes = Math.floor(diff / 60000)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const d = new Date(then)
  const month = d.toLocaleString('en', { month: 'short' })
  return `${month} ${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function formatDuration(ms) {
  if (ms == null) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function formatAbsolute(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso || '—'
  return d.toLocaleString()
}

// The request body is stored verbatim (a truncated or malformed body must
// still render), so this is a display parse: it never throws.
export function parseRequestBody(raw) {
  if (typeof raw !== 'string' || !raw) return { ok: false }
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && Array.isArray(parsed.messages)) {
      return { ok: true, body: parsed }
    }
    return { ok: false }
  } catch {
    return { ok: false }
  }
}

// The body is stored minified as the client sent it, and a 1 MB-truncated
// body is not valid JSON, so this never throws and falls back to the raw text.
export function prettyJsonBody(raw) {
  if (typeof raw !== "string" || !raw) return { text: raw ?? "", pretty: false }
  try {
    return { text: JSON.stringify(JSON.parse(raw), null, 2), pretty: true }
  } catch {
    return { text: raw, pretty: false }
  }
}

export function prettyArguments(rawArgs) {
  if (rawArgs == null) return { text: '', valid: true }
  const text = typeof rawArgs === 'string' ? rawArgs : JSON.stringify(rawArgs, null, 2)
  if (typeof rawArgs === 'object') return { text, valid: true }
  try {
    return { text: JSON.stringify(JSON.parse(text), null, 2), valid: true }
  } catch {
    return { text, valid: false }
  }
}

export function messageContentChars(content) {
  if (typeof content === 'string') return content.length
  if (Array.isArray(content)) {
    return content.reduce(
      (sum, part) => sum + (part && typeof part.text === 'string' ? part.text.length : 0),
      0
    )
  }
  return 0
}

export function approxImageSize(url) {
  if (typeof url !== 'string') return 'n/a'
  if (url.startsWith('data:')) {
    const comma = url.indexOf(',')
    const b64 = comma >= 0 ? url.slice(comma + 1) : url
    const bytes = Math.round(b64.length * 0.75)
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }
  return 'n/a'
}

// Same insecure-origin fallback as CopyablePre: navigator.clipboard is
// missing on plain-HTTP origins reached over the tunnel without TLS.
export async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch { /* fall through */ }
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.position = 'fixed'
  ta.style.top = '-1000px'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try { ok = document.execCommand('copy') } catch { /* clipboard unavailable */ }
  document.body.removeChild(ta)
  return ok
}
