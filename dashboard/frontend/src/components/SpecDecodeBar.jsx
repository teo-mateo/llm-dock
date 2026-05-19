import { useMemo } from 'react'

export default function SpecDecodeBar({ specPerPos }) {
  const entries = useMemo(() => {
    if (!specPerPos || Object.keys(specPerPos).length === 0) return []
    return Object.entries(specPerPos)
  }, [specPerPos])

  const maxVal = useMemo(() => {
    return Math.max(1, ...entries.map(([, v]) => v))
  }, [entries])

  if (entries.length === 0) return null

  return (
    <div className="bg-surface rounded-lg border border-border p-4">
      <h3 className="text-sm font-medium text-fg-muted mb-3">Spec Decode per Position</h3>
      <div className="space-y-2">
        {entries.map(([key, val]) => {
          const pct = (val / maxVal) * 100
          const label = key.replace('position_', 'Pos ')
          return (
            <div key={key} className="flex items-center gap-2">
              <span className="text-fg-muted text-xs w-10 text-right">{label}</span>
              <div className="flex-1 bg-surface-strong rounded h-4 overflow-hidden">
                <div className="h-full bg-warning rounded" style={{ width: `${pct}%` }} />
              </div>
              <span className="text-fg-muted text-xs w-8 text-right">{Math.round(val)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
