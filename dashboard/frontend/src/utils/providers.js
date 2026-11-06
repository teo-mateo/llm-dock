const PROVIDER_ID_RE = /^[a-z][a-z0-9-]{1,31}$/

// Mirror of chat/providers.py:parse_service — `<provider-id>:<model-id>`.
// Syntax only, so a deleted provider's conversations still read as provider models.
export function parseProviderService(name) {
  if (typeof name !== 'string') return null
  const i = name.indexOf(':')
  if (i < 0) return null
  const providerId = name.slice(0, i)
  const modelId = name.slice(i + 1)
  if (providerId === 'openrouter' || !PROVIDER_ID_RE.test(providerId) || !modelId) return null
  return { providerId, modelId }
}

export const isProviderService = (name) => parseProviderService(name) !== null

export const providerServiceName = (providerId, modelId) => `${providerId}:${modelId}`
