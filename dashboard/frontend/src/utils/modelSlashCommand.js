import { isOpenRouterService, openRouterModelId, serviceNameForModel } from './openrouter'
import { parseProviderService, providerServiceName } from './providers'

export function parseModelCommand(text) {
  if (typeof text !== 'string') return null
  if (text.includes('\n')) return null
  const t = text.trim()
  if (t === '/model') return { arg: null }
  const m = /^\/model[ \t]+(.*)$/.exec(t)
  if (!m) return null
  const arg = m[1].trim()
  return { arg: arg || null }
}

export function resolveModelRef(arg, models = {}) {
  if (typeof arg !== 'string' || !arg) return null
  const { services = [], openRouterModels = [], providerGroups = [] } = models

  for (const s of services) {
    if (s.name === arg) return arg
  }
  if (isOpenRouterService(arg) && openRouterModelId(arg)) return arg
  const provider = parseProviderService(arg)
  if (provider) {
    const group = providerGroups.find(g => g.id === provider.providerId)
    if (group) return providerServiceName(provider.providerId, provider.modelId)
    return null
  }
  if (arg.includes(':')) return null

  const curated = openRouterModels.find(m => m.id === arg || m.label === arg)
  if (curated) return serviceNameForModel(curated.id)
  for (const group of providerGroups) {
    const model = (group.models || []).find(m => m.id === arg || m.label === arg)
    if (model) return providerServiceName(group.id, model.id)
  }
  return null
}

export function formatModelList(models = {}) {
  const { services = [], openRouterModels = [], providerGroups = [] } = models
  const lines = []
  if (services.length > 0) {
    lines.push('Local models:')
    for (const s of services) {
      lines.push(`  ${s.name} (${s.status === 'running' ? 'running' : 'stopped'})`)
    }
  }
  if (openRouterModels.length > 0) {
    lines.push('OpenRouter:')
    for (const m of openRouterModels) {
      lines.push(`  ${serviceNameForModel(m.id)}`)
    }
  }
  for (const group of providerGroups) {
    const ms = group.models || []
    if (ms.length === 0) continue
    lines.push(`${group.name || group.id}:`)
    for (const m of ms) {
      lines.push(`  ${providerServiceName(group.id, m.id)}`)
    }
  }
  if (lines.length === 0) lines.push('No models available.')
  return lines
}
