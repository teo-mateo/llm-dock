import useRunningServices from '../../hooks/useRunningServices'
import useOpenRouterModels from '../../hooks/useOpenRouterModels'
import { isOpenRouterService, openRouterModelId, serviceNameForModel } from '../../utils/openrouter'

// One dropdown's options: local running services + curated OpenRouter models.
// `selected` may reference an OpenRouter model that was since removed from
// the curated list (or a key that got unset) — keep it visible as a fallback
// option so the native select doesn't render blank and the persisted value
// survives an unrelated save.
function ModelOptions({ services, openRouterModels, selected }) {
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

export default function ModelSelector({ mainService, sidekickService, onChangeMain, onChangeSidekick, disabled }) {
  const { services, loading } = useRunningServices()
  const { data: openRouterData, loading: openRouterLoading } = useOpenRouterModels()

  if (loading || openRouterLoading) {
    return <div className="text-xs text-fg-subtle">Loading services...</div>
  }

  const openRouterModels = openRouterData?.configured ? openRouterData.current : []

  return (
    <div className="flex gap-4 items-center flex-wrap">
      <div className="flex items-center gap-2">
        <label className="text-xs text-fg-muted whitespace-nowrap">Main:</label>
        <select
          value={mainService}
          onChange={e => onChangeMain(e.target.value)}
          disabled={disabled}
          className="bg-surface border border-border rounded px-2 py-1 text-xs text-fg disabled:opacity-50"
        >
          <option value="">Select model...</option>
          <ModelOptions services={services} openRouterModels={openRouterModels} selected={mainService} />
        </select>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs text-fg-muted whitespace-nowrap">Critic:</label>
        <select
          value={sidekickService || ''}
          onChange={e => onChangeSidekick(e.target.value || null)}
          disabled={disabled}
          className="bg-surface border border-border rounded px-2 py-1 text-xs text-fg disabled:opacity-50"
        >
          <option value="">None</option>
          <ModelOptions services={services} openRouterModels={openRouterModels} selected={sidekickService} />
        </select>
      </div>
    </div>
  )
}
