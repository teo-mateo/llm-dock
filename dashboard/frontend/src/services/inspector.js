import { fetchAPI } from '../api'

export function listCaptures({ service = null, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams()
  if (service) params.set('service', service)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return fetchAPI(`/inspector/captures?${params}`)
}

export function getCapture(captureId) {
  return fetchAPI(`/inspector/captures/${encodeURIComponent(captureId)}`)
}

export function deleteCaptures(service = null) {
  const qs = service ? `?service=${encodeURIComponent(service)}` : ''
  return fetchAPI(`/inspector/captures${qs}`, { method: 'DELETE' })
}

export function inspectorServices() {
  return fetchAPI('/inspector/services')
}
