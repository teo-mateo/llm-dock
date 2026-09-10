import useRunningServices from '../../hooks/useRunningServices'

// Per-conversation reasoning-level picker, rendered beside the model selector.
//
// Renders nothing when the selected service declares no ladder: a control that
// can only ever be ignored is worse than no control. The ladder comes from the
// service payload, which is the same list the server validates against, so what
// is offered here is exactly what can reach the model.
//
// "Model default" is not the same choice as an "off" level. It stores null,
// which sends no reasoning field at all — the request an un-featured service
// makes. `off`, when a service declares it, actively instructs the model not to
// think. Levels are the model's own token names, shown verbatim and in the
// order the operator declared them.
export default function ReasoningLevelSelect({ mainService, value, onChange, disabled }) {
  const { services, loading } = useRunningServices()

  if (loading || !onChange || !mainService) return null

  const service = services.find(s => s.name === mainService)
  const levels = service?.reasoning_levels || []
  if (levels.length === 0) return null

  // A stored level the service no longer declares is still shown (and still
  // will not be sent — the server drops it and says so on run_started). Hiding
  // it would make the conversation look like it was thinking.
  const stale = !!value && !levels.some(l => l.id === value)

  return (
    <div className="flex items-center gap-2">
      <label
        className="text-xs text-fg-muted whitespace-nowrap"
        htmlFor="reasoning-level-select"
        title="Reasoning level. These are the model's own level names, not token budgets: a level is an instruction to the model's chat template, and how much it thinks is the model's choice."
      >
        Reasoning:
      </label>
      <select
        id="reasoning-level-select"
        data-testid="reasoning-level-select"
        value={value || ''}
        onChange={e => onChange(e.target.value === '' ? null : e.target.value)}
        disabled={disabled}
        className="bg-surface border border-border rounded px-2 py-1 text-xs text-fg disabled:opacity-50"
      >
        <option value="">Model default</option>
        {levels.map(l => (
          <option key={l.id} value={l.id}>{l.id}</option>
        ))}
        {stale && (
          <option value={value}>{value} (not offered by this model)</option>
        )}
      </select>
    </div>
  )
}
