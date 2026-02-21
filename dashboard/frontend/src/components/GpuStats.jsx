export default function GpuStats({ gpu }) {
  const memPct = Math.round((gpu.memory.used / gpu.memory.total) * 100)

  return (
    <div className="w-[500px] shrink-0 bg-gray-800 border border-gray-700 rounded-lg p-4">
      {/* GPU Name */}
      <div className="flex items-center gap-2 mb-4">
        <i className="fa-solid fa-microchip text-green-400" />
        <span className="font-bold text-base">{gpu.name}</span>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
        {/* Memory */}
        <div>
          <p className="text-gray-400 mb-1">Memory</p>
          <p className="font-mono text-white">{gpu.memory.used}/{gpu.memory.total} MiB</p>
          <div className="w-full bg-gray-700 rounded h-1.5 mt-1">
            <div className="bg-blue-500 h-1.5 rounded" style={{ width: `${memPct}%` }} />
          </div>
        </div>

        {/* Temperature */}
        <div>
          <p className="text-gray-400 mb-1">Temperature</p>
          <p className="font-mono text-white">{gpu.temperature.current}°C</p>
        </div>

        {/* GPU Utilization */}
        <div>
          <p className="text-gray-400 mb-1">GPU Utilization</p>
          <p className="font-mono text-white">{gpu.utilization.gpu_percent}%</p>
        </div>

        {/* Power */}
        <div>
          <p className="text-gray-400 mb-1">Power</p>
          <p className="font-mono text-white">{gpu.power.draw.toFixed(1)}/{gpu.power.limit.current.toFixed(0)} W</p>
        </div>
      </div>
    </div>
  )
}
