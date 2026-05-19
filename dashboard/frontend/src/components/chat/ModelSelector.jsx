import useRunningServices from '../../hooks/useRunningServices'

export default function ModelSelector({ mainService, sidekickService, onChangeMain, onChangeSidekick, disabled }) {
  const { services, loading } = useRunningServices()

  if (loading) {
    return <div className="text-xs text-fg-subtle">Loading services...</div>
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
          {services.map(s => (
            <option key={s.name} value={s.name}>{s.name}</option>
          ))}
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
          {services.map(s => (
            <option key={s.name} value={s.name}>{s.name}</option>
          ))}
        </select>
      </div>
    </div>
  )
}
