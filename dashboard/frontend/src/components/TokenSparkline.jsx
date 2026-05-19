import { useEffect, useRef } from 'react'
import { useTheme } from '../contexts/ThemeContext'

const MAX_POINTS = 50 // 50 × 200ms = 10s of history

// Canvas is immediate-mode; read resolved token values at draw time so a
// theme swap repaints with the right colors (issue #5 §8).
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

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
  ctx.strokeStyle = cssVar('--color-chart-grid')
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
    ctx.fillStyle = cssVar('--color-fg-subtle')
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

  drawLine(dp => dp.promptTokensRate || 0, cssVar('--color-chart-memory'))
  drawLine(dp => dp.generationTokensRate || 0, cssVar('--color-chart-compute'))
}

export default function TokenSparkline({ history }) {
  const canvasRef = useRef(null)
  const { theme } = useTheme()

  useEffect(() => {
    if (canvasRef.current) draw(canvasRef.current, history)
  }, [history, theme])

  const latest = history.length > 0 ? history[history.length - 1] : null
  const promptRate = latest?.promptTokensRate
  const genRate = latest?.generationTokensRate
  const visiblePoints = history.slice(-MAX_POINTS)
  const promptMax = visiblePoints.length >= 2 ? Math.max(1, ...visiblePoints.map(p => p.promptTokensRate || 0)) : null
  const genMax = visiblePoints.length >= 2 ? Math.max(1, ...visiblePoints.map(p => p.generationTokensRate || 0)) : null

  return (
    <div className="bg-surface rounded-lg border border-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-fg-muted">Token Throughput</h3>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-chart-memory rounded inline-block" />
            <span className="text-fg-muted">Prompt:</span>
            {promptMax !== null && <span className="text-fg-subtle">max {promptMax.toFixed(1)} t/s</span>}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-chart-compute rounded inline-block" />
            <span className="text-fg-muted">Gen:</span>
            {genMax !== null && <span className="text-fg-subtle">max {genMax.toFixed(1)} t/s</span>}
          </div>
        </div>
      </div>
      <div className="relative h-[160px]">
        <canvas ref={canvasRef} className="w-full h-full" />
      </div>
      {latest && (
        <div className="mt-2 text-xs font-mono flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-chart-memory rounded inline-block" />
            <span className="text-fg-muted">Prompt:</span>
            <span className="text-fg-muted">{promptRate !== undefined ? `${promptRate.toFixed(1)} t/s` : '—'}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-chart-compute rounded inline-block" />
            <span className="text-fg-muted">Gen:</span>
            <span className="text-fg-muted">{genRate !== undefined ? `${genRate.toFixed(1)} t/s` : '—'}</span>
          </div>
        </div>
      )}
    </div>
  )
}
