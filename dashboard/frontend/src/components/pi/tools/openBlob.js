const OPENED_URL_LIFETIME_MS = 60_000

const BROWSER = {
  open: (url) => window.open(url, '_blank', 'noopener'),
  createUrl: (blob) => URL.createObjectURL(blob),
  revokeUrl: (url) => URL.revokeObjectURL(url),
  schedule: (fn, ms) => setTimeout(fn, ms),
}

export function openBlob(blob, deps = BROWSER) {
  if (blob == null) return
  const url = deps.createUrl(blob)
  deps.open(url)
  deps.schedule(() => deps.revokeUrl(url), OPENED_URL_LIFETIME_MS)
}
