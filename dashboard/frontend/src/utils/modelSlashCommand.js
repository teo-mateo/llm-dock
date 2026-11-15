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

// Exact service strings (openrouter:/provider:) resolve only when offered or
// already the current model: the server stores main_service unvalidated, so
// accepting a typo'd string would report a successful switch and only fail at
// run time — strictly worse than the picker, which cannot produce it.
export function resolveModelRef(arg, models = {}) {
  if (typeof arg !== 'string' || !arg) return null
  const { services = [], openRouterModels = [], providerGroups = [], currentService } = models

  for (const s of services) {
    if (s.name === arg) return { service: arg }
  }
  if (arg.includes(':')) {
    if (arg === currentService) return { service: arg }
    if (isOpenRouterService(arg) && openRouterModelId(arg)) {
      if (openRouterModels.some(m => serviceNameForModel(m.id) === arg)) return { service: arg }
      return null
    }
    const provider = parseProviderService(arg)
    if (provider) {
      const group = providerGroups.find(g => g.id === provider.providerId)
      if (group && (group.models || []).some(m => m.id === provider.modelId)) {
        return { service: arg }
      }
    }
    return null
  }

  const candidates = new Set()
  for (const m of openRouterModels) {
    if (m.id === arg || fold(m.label) === fold(arg)) candidates.add(serviceNameForModel(m.id))
  }
  for (const group of providerGroups) {
    for (const m of group.models || []) {
      if (m.id === arg || fold(m.label) === fold(arg)) candidates.add(providerServiceName(group.id, m.id))
    }
  }
  if (candidates.size === 0) return null
  if (candidates.size > 1) return { ambiguous: [...candidates] }
  return { service: candidates.values().next().value }
}

function fold(s) {
  return typeof s === 'string' ? s.toLowerCase() : ''
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
