const CIRCUMFERENCE = 2 * Math.PI * 18

// Categorical threshold hexes stay JS constants (not theme-driven): they
// must read identically and are asserted by GaugesRow.test (issue #5 §8).
// Only the non-threshold SVG chrome (track, label text) is themed, via
// CSS-driven stroke-/fill- utilities that re-resolve on a theme swap.
const kvColor = (pct) => {
  if (pct < 60) return '#22c55e'
  if (pct <= 85) return '#eab308'
  return '#ef4444'
}

function DonutGauge({ value, label, colorGetter }) {
  const displayVal = value !== undefined && value !== null ? value : undefined
  const displayPct = displayVal !== undefined && !Number.isNaN(displayVal) ? Math.max(0, Math.min(100, displayVal)) : undefined
  const color = displayPct !== undefined ? (typeof colorGetter === 'function' ? colorGetter(displayPct) : colorGetter) : null

  return (
    <div className="flex flex-col items-center gap-1.5">
      <svg width="48" height="48" viewBox="0 0 48 48">
        <circle className="stroke-chart-grid" cx="24" cy="24" r={18} fill="none" strokeWidth={4} strokeDasharray={CIRCUMFERENCE} />
        {displayPct !== undefined && color && (
          <circle
            cx="24"
            cy="24"
            r={18}
            fill="none"
            stroke={color}
            strokeWidth={4}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - displayPct / 100)}
            strokeLinecap="round"
            transform="rotate(-90 24 24)"
          />
        )}
        <text
          x="24"
          y="24"
          dominantBaseline="central"
          textAnchor="middle"
          className="fill-chart-axis-label"
          fontSize="9"
          fontWeight="600"
        >
          {displayPct !== undefined ? `${Math.round(displayPct)}%` : '—'}
        </text>
      </svg>
      <span className="text-fg-muted text-xs">{label}</span>
    </div>
  )
}

export default function GaugesRow({ kvCache, prefixHitRatio, specAcceptRatio }) {
  const kvPct = kvCache !== undefined && kvCache !== null ? kvCache * 100 : undefined
  const prefixPct = prefixHitRatio !== undefined && prefixHitRatio !== null ? prefixHitRatio * 100 : undefined
  const specPct = specAcceptRatio !== undefined && specAcceptRatio !== null ? specAcceptRatio * 100 : undefined

  return (
    <div className="bg-surface rounded-lg border border-border p-4">
      <h3 className="text-sm font-medium text-fg-muted mb-3">Utilization</h3>
      <div className="flex justify-around items-center">
        <div title="KV blocks actively used by running/waiting requests (not prefix-cached blocks).">
          <DonutGauge value={kvPct} label="Active KV" colorGetter={kvColor} />
        </div>
        <DonutGauge value={prefixPct} label="Prefix Hit %" colorGetter="#3b82f6" />
        <DonutGauge value={specPct} label="Spec Accept %" colorGetter="#a855f7" />
      </div>
    </div>
  )
}
