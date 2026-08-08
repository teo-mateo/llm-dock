import { isOpenRouterService, openRouterModelId, serviceNameForModel } from '../../utils/openrouter'

// One dropdown's options: local running services + curated OpenRouter models.
// `selected` may reference an OpenRouter model that was since removed from
// the curated list (or a key that got unset) — keep it visible as a fallback
// option so the native select doesn't render blank and the persisted value
// survives an unrelated save.
export default function ModelOptions({ services, openRouterModels, selected }) {
  const openRouterValues = openRouterModels.map(m => serviceNameForModel(m.id))
  const stale =
    isOpenRouterService(selected) && !openRouterValues.includes(selected)
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
      {stale && (
        <option value={selected}>{openRouterModelId(selected)} (not in list)</option>
      )}
    </>
  )
}
