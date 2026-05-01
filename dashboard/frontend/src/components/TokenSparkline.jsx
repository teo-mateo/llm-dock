import { useEffect, useRef } from 'react'

const MAX_POINTS = 50 // 50 × 200ms = 10s of history

function draw(canvas, history) {
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

  // Limit history to MAX_POINTS to prevent canvas spill
  const points = history.slice(-MAX_POINTS)
  const len = points.length

  if (len < 2) {
    ctx.fillStyle = '#6b7280'
    ctx.font = '13px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('Awaiting data points...', width / 2, height / 2)
    return
  }

  const pointW = (width - 2 * pad) / (MAX_POINTS - 1)

  const drawLine = (selector, color) => {
    const data = points.map(selector)
    const lineMax = Math.max(1, ...data)
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.beginPath()
    data.forEach((val, i) => {
      const x = width - pad - (len - 1 - i) * pointW
      const y = height - pad - (val / lineMax) * (height - 2 * pad)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.stroke()
  }

  drawLine(dp => dp.promptTokensRate || 0, '#3b82f6')
  drawLine(dp => dp.generationTokensRate || 0, '#22c55e')
}

export default function TokenSparkline({ history }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    if (canvasRef.current) draw(canvasRef.current, history)
  }, [history])

  const latest = history.length > 0 ? history[history.length - 1] : null
  const promptRate = latest?.promptTokensRate
  const genRate = latest?.generationTokensRate
  const visiblePoints = history.slice(-MAX_POINTS)
  const promptMax = visiblePoints.length >= 2 ? Math.max(1, ...visiblePoints.map(p => p.promptTokensRate || 0)) : null
  const genMax = visiblePoints.length >= 2 ? Math.max(1, ...visiblePoints.map(p => p.generationTokensRate || 0)) : null

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-400">Token Throughput</h3>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 bg-blue-500 rounded" />
            <span className="text-gray-400">Prompt</span>
            {promptMax !== null && <span className="text-gray-500">max {promptMax.toFixed(1)}</span>}
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 bg-green-500 rounded" />
            <span className="text-gray-400">Gen</span>
            {genMax !== null && <span className="text-gray-500">max {genMax.toFixed(1)}</span>}
          </div>
        </div>
      </div>
      <div className="relative h-[160px]">
        <canvas ref={canvasRef} className="w-full h-full" />
      </div>
      {latest && (
        <div className="mt-2 text-xs text-gray-400 font-mono">
          Prompt: {promptRate !== undefined ? `${promptRate.toFixed(1)} t/s` : '—'} | Gen: {genRate !== undefined ? `${genRate.toFixed(1)} t/s` : '—'}
        </div>
      )}
    </div>
  )
}
