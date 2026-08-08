import useRunningServices from '../../hooks/useRunningServices'
import useOpenRouterModels from '../../hooks/useOpenRouterModels'
import ModelOptions from './ModelOptions'

// Single labeled model dropdown shared by the conversation header (via
// ModelSelector) and the new-chat empty-state composer (variant="new-chat").
// `variant="new-chat"` renders only the main model select — no Critic, no
// empty "Select model..." placeholder — because the empty-state composer
// always has a pre-selected model.
export default function ModelSelector({
  mainService,
  sidekickService,
  onChangeMain,
  onChangeSidekick,
  disabled,
  variant = 'full',
}) {
  const { services, loading } = useRunningServices()
  const { data: openRouterData, loading: openRouterLoading } = useOpenRouterModels()

  if (loading || openRouterLoading) {
    return <div className="text-xs text-fg-subtle">Loading services...</div>
  }

  const openRouterModels = openRouterData?.configured ? openRouterData.current : []

  if (variant === 'new-chat') {
    return (
      <div className="flex items-center gap-2">
        <label className="text-xs text-fg-muted whitespace-nowrap">Model:</label>
        <select
          value={mainService || ''}
          onChange={e => onChangeMain(e.target.value)}
          disabled={disabled}
          className="bg-surface border border-border rounded px-2 py-1 text-xs text-fg disabled:opacity-50"
        >
          <ModelOptions services={services} openRouterModels={openRouterModels} selected={mainService} />
        </select>
      </div>
    )
  }

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
