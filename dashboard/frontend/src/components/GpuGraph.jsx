import { useEffect, useRef } from 'react'

const MAX_POINTS = 20

function draw(canvas, memoryHistory, computeHistory) {
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  const width = rect.width
  const height = rect.height

  canvas.width = width * dpr
  canvas.height = height * dpr
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, width, height)

  const pad = 2

  // Grid lines
  ctx.strokeStyle = '#374151'
  ctx.lineWidth = 0.5
  for (let i = 0; i <= 4; i++) {
    const y = pad + (height - 2 * pad) * (i / 4)
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(width, y)
    ctx.stroke()
  }

  if (memoryHistory.length < 2) return

  const pointW = (width - 2 * pad) / (MAX_POINTS - 1)
  const len = memoryHistory.length

  const drawLine = (data, color) => {
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.beginPath()
    data.forEach((val, i) => {
      const x = width - pad - (len - 1 - i) * pointW
      const y = height - pad - (val / 100) * (height - 2 * pad)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.stroke()
  }

  drawLine(memoryHistory, '#3b82f6')
  drawLine(computeHistory, '#22c55e')
}

export default function GpuGraph({ memoryHistory, computeHistory }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    if (canvasRef.current) {
      draw(canvasRef.current, memoryHistory, computeHistory)
    }
  }, [memoryHistory, computeHistory])

  return (
    <div className="flex-1 min-w-0 pt-1">
      <div className="flex items-center justify-between mb-2">
        <p className="text-gray-400 text-xs">GPU History (60s)</p>
        <div className="flex gap-3 text-xs">
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 bg-blue-500 rounded" />
            Memory
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 bg-green-500 rounded" />
            Compute
          </span>
        </div>
      </div>
      <canvas ref={canvasRef} className="w-full h-[120px] rounded" />
    </div>
  )
}
