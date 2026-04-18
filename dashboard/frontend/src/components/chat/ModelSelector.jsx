import useRunningServices from '../../hooks/useRunningServices'

export default function ModelSelector({ mainService, sidekickService, onChangeMain, onChangeSidekick, disabled }) {
  const { services, loading } = useRunningServices()

  if (loading) {
    return <div className="text-xs text-gray-500">Loading services...</div>
  }

  return (
    <div className="flex gap-4 items-center flex-wrap">
      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-400 whitespace-nowrap">Main:</label>
        <select
          value={mainService}
          onChange={e => onChangeMain(e.target.value)}
          disabled={disabled}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 disabled:opacity-50"
        >
          <option value="">Select model...</option>
          {services.map(s => (
            <option key={s.name} value={s.name}>{s.name}</option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-400 whitespace-nowrap">Sidekick:</label>
        <select
          value={sidekickService || ''}
          onChange={e => onChangeSidekick(e.target.value || null)}
          disabled={disabled}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 disabled:opacity-50"
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
