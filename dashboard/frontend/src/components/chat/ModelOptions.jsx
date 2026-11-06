import { isOpenRouterService, openRouterModelId, serviceNameForModel } from '../../utils/openrouter'
import { parseProviderService, providerServiceName } from '../../utils/providers'

// One dropdown's options: local running services, curated OpenRouter models, then
// one group per configured provider. `selected` may reference a model that is no
// longer offered (removed from the list, provider deleted, key unset) — keep it
// visible as a fallback option so the native select doesn't render blank and the
// persisted value survives an unrelated save.
export default function ModelOptions({ services, openRouterModels, providerGroups = [], selected }) {
  const openRouterValues = openRouterModels.map(m => serviceNameForModel(m.id))
  const providerValues = providerGroups.flatMap(g => g.models.map(m => providerServiceName(g.id, m.id)))
  const staleOpenRouter = isOpenRouterService(selected) && !openRouterValues.includes(selected)
  const staleProvider = parseProviderService(selected)
  const showStaleProvider = staleProvider && !providerValues.includes(selected)
  return (
    <>
      {services.length > 0 && (
        <optgroup label="Local">
          {services.map(s => (
            <option key={s.name} value={s.name}>{s.name}</option>
          ))}
        </optgroup>
      )}
      {openRouterModels.length > 0 && (
        <optgroup label="OpenRouter">
          {openRouterModels.map(m => (
            <option key={m.id} value={serviceNameForModel(m.id)}>{m.label}</option>
          ))}
        </optgroup>
      )}
      {providerGroups.map(g => (
        <optgroup key={g.id} label={g.name}>
          {g.models.map(m => (
            <option key={m.id} value={providerServiceName(g.id, m.id)}>{m.label}</option>
          ))}
        </optgroup>
      ))}
      {staleOpenRouter && (
        <option value={selected}>{openRouterModelId(selected)} (not in list)</option>
      )}
      {showStaleProvider && (
        <option value={selected}>{staleProvider.modelId} · {staleProvider.providerId} (not available)</option>
      )}
    </>
  )
}
