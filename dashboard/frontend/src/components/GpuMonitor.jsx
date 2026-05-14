import { useState, useEffect } from 'react'
import useGpuSSE from '../hooks/useGpuSSE'
import GpuStats from './GpuStats'
import GpuGraph from './GpuGraph'

const MAX_POINTS = 20 // 20 frames × ~3s server tick = ~60s of history

function updateHistories(prev, gpus) {
  const next = { ...prev }
  for (const g of gpus) {
    const h = next[g.index]
      ? { memory: [...next[g.index].memory], compute: [...next[g.index].compute] }
      : { memory: [], compute: [] }
    h.memory.push(Math.round((g.memory.used / g.memory.total) * 100))
    h.compute.push(g.utilization.gpu_percent)
    if (h.memory.length > MAX_POINTS) h.memory.shift()
    if (h.compute.length > MAX_POINTS) h.compute.shift()
    next[g.index] = h
  }
  return next
}

export default function GpuMonitor() {
  const { gpus, error } = useGpuSSE()
  const [histories, setHistories] = useState({})

  useEffect(() => {
    if (gpus && gpus.length) {
      setHistories(prev => updateHistories(prev, gpus))
    }
  }, [gpus])

  if (error) {
    return <p className="text-red-400">GPU: {error}</p>
  }

  if (gpus === null) {
    return <p className="text-gray-500">Loading GPU info...</p>
  }

  if (!gpus.length) {
    return <p className="text-gray-400">No GPU detected</p>
  }

  return (
    <div className="flex flex-col gap-4">
      {gpus.map(gpu => {
        const h = histories[gpu.index] || { memory: [], compute: [] }
        return (
          <div key={gpu.index} className="flex gap-4 items-center">
            <GpuStats gpu={gpu} />
            <GpuGraph memoryHistory={h.memory} computeHistory={h.compute} />
          </div>
        )
      })}
    </div>
  )
}
