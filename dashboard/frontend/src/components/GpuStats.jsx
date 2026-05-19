export default function GpuStats({ gpu }) {
  const memPct = Math.round((gpu.memory.used / gpu.memory.total) * 100)

  return (
    <div className="w-[500px] shrink-0 bg-surface border border-border rounded-lg p-4">
      {/* GPU Name */}
      <div className="flex items-center gap-2 mb-4">
        <i className="fa-solid fa-microchip text-success-fg" />
        <span className="font-bold text-base">{gpu.name}</span>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
        {/* Memory */}
        <div>
          <p className="text-fg-muted mb-1">Memory</p>
          <p className="font-mono text-fg">{gpu.memory.used}/{gpu.memory.total} MiB</p>
          <div className="w-full bg-surface-strong rounded h-1.5 mt-1">
            <div className="bg-accent h-1.5 rounded" style={{ width: `${memPct}%` }} />
          </div>
        </div>

        {/* Temperature */}
        <div>
          <p className="text-fg-muted mb-1">Temperature</p>
          <p className="font-mono text-fg">{gpu.temperature.current}°C</p>
        </div>

        {/* GPU Utilization */}
        <div>
          <p className="text-fg-muted mb-1">GPU Utilization</p>
          <p className="font-mono text-fg">{gpu.utilization.gpu_percent}%</p>
        </div>

        {/* Power */}
        <div>
          <p className="text-fg-muted mb-1">Power</p>
          <p className="font-mono text-fg">{gpu.power.draw.toFixed(1)}/{gpu.power.limit.current.toFixed(0)} W</p>
        </div>
      </div>
    </div>
  )
}
