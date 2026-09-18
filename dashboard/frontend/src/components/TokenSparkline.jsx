import { useEffect, useMemo, useRef } from 'react'
import { useTheme } from '../contexts/ThemeContext'
import { MAX_POINTS, SMOOTH_LABEL, SMOOTH_POINTS, advanceScale, prepareSeries } from '../tokenSeries'
import {
  IDLE_GEN_RATE,
  RUNNER_FRAMES,
  RUNNER_PIXEL,
  RUNNER_STAND,
  drawRunner,
  frameSize,
  runnerFrame,
  poseStepsPerSecond,
} from '../runnerSprite'

// Canvas is immediate-mode; read resolved token values at draw time so a
// theme swap repaints with the right colors (issue #5 §8).
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function labelTps(n) {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return n.toFixed(1)
}

function draw(canvas, series, scale, frame) {
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  const width = rect.width
  const height = rect.height

  // Assigning canvas.width discards and reallocates the backing store, so only do
  // it when the box actually changed — the animation loop would otherwise pay for
  // it every stride. setTransform (not scale) because a skipped assignment keeps
  // the previous transform.
  const deviceW = Math.round(width * dpr)
  const deviceH = Math.round(height * dpr)
  if (canvas.width !== deviceW || canvas.height !== deviceH) {
    canvas.width = deviceW
    canvas.height = deviceH
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, width, height)

  const len = series.length
  const labelW = 44
  const pad = 2
  const chartX = labelW
  const chartW = width - 2 * labelW
  const chartRight = chartX + chartW

  // Prefill runs 10-100x faster than decode, so a shared scale would flatten
  // the gen line. Each line keeps its own scale, with its axis labels drawn
  // in the line's color: prompt on the left, gen on the right.
  const { promptMax, genMax } = scale

  // Grid lines
  ctx.strokeStyle = cssVar('--color-chart-grid')
  ctx.lineWidth = 0.5
  for (let i = 0; i <= 4; i++) {
    const y = pad + (height - 2 * pad) * (i / 4)
    ctx.beginPath()
    ctx.moveTo(chartX, y)
    ctx.lineTo(chartRight, y)
    ctx.stroke()
  }

  if (len < 2) {
    ctx.fillStyle = cssVar('--color-fg-subtle')
    ctx.font = '13px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText('Awaiting data points...', chartX + chartW / 2, height / 2)
    return
  }

  const pointW = chartW / (MAX_POINTS - 1)

  // Y-axis labels
  ctx.font = '9px sans-serif'
  ctx.textBaseline = 'middle'
  const drawAxis = (max, color, align, x) => {
    ctx.fillStyle = color
    ctx.textAlign = align
    for (let i = 0; i <= 4; i++) {
      const val = max * (1 - i / 4)
      const y = pad + (height - 2 * pad) * (i / 4)
      ctx.fillText(labelTps(val), x, y)
    }
  }
  drawAxis(promptMax, cssVar('--color-chart-memory'), 'right', chartX - 4)
  drawAxis(genMax, cssVar('--color-chart-compute'), 'left', chartRight + 4)

  const yOf = (val, max) => height - pad - (val / max) * (height - 2 * pad)

  const drawLine = (data, max, color, lineWidth, alpha) => {
    ctx.strokeStyle = color
    ctx.lineWidth = lineWidth
    ctx.globalAlpha = alpha
    ctx.beginPath()
    data.forEach((val, i) => {
      const x = chartRight - (len - 1 - i) * pointW
      const y = yOf(val, max)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    })
    ctx.stroke()
    ctx.globalAlpha = 1
  }

  // Raw scrapes under the smoothed line, so the presented trend keeps the
  // burstiness that produced it on screen.
  if (SMOOTH_POINTS > 1) {
    drawLine(series.promptRaw, promptMax, cssVar('--color-chart-memory'), 1, 0.22)
    drawLine(series.genRaw, genMax, cssVar('--color-chart-compute'), 1, 0.22)
  }
  drawLine(series.prompt, promptMax, cssVar('--color-chart-memory'), 2, 1)
  drawLine(series.gen, genMax, cssVar('--color-chart-compute'), 2, 1)

  // The runner stands with his leading foot on the newest smoothed gen point, in
  // the card's ink colour with a green scarf, flush with the plot's right edge so
  // he touches the line's tip and stays clear of the axis labels in the gutter.
  const size = frameSize(RUNNER_FRAMES[frame])
  const feetY = Math.min(Math.max(yOf(series.gen[len - 1], genMax), pad + size.height * RUNNER_PIXEL), height - pad)
  drawRunner(ctx, RUNNER_FRAMES[frame], chartRight - size.width * RUNNER_PIXEL, feetY, {
    ink: cssVar('--color-fg'),
    accent: cssVar('--color-chart-compute'),
  })
}

export default function TokenSparkline({ history }) {
  const canvasRef = useRef(null)
  const { theme } = useTheme()
  const series = useMemo(() => prepareSeries(history), [history])
  const genAxisRef = useRef({ scale: null, raisedAt: 0 })
  const seriesRef = useRef(series)
  const scaleRef = useRef({ promptMax: 1, genMax: 1 })
  const phaseRef = useRef(0)
  const rateRef = useRef(0)
  const frameRef = useRef(RUNNER_STAND)

  const genRate = series.length > 0 ? series.gen[series.gen.length - 1] : 0
  const running = genRate > IDLE_GEN_RATE

  useEffect(() => {
    seriesRef.current = series
    rateRef.current = genRate
    if (!canvasRef.current) return
    const held = advanceScale(genAxisRef.current, series.genCeiling, Date.now() / 1000)
    genAxisRef.current = held
    const scale = { promptMax: series.promptCeiling, genMax: held.scale }
    scaleRef.current = scale
    frameRef.current = running ? runnerFrame(phaseRef.current) : RUNNER_STAND
    draw(canvasRef.current, series, scale, frameRef.current)
  }, [series, theme, running, genRate])

  // The stride loop: paints only when the pose changed, so a running service costs
  // a handful of repaints per second rather than one per animation frame, and a
  // stopped service costs none — no loop is scheduled at all.
  useEffect(() => {
    if (!running) return
    let raf
    let prev = performance.now()
    const tick = () => {
      // Wall clock, not the rAF argument: jsdom calls back with no timestamp, which
      // would make the elapsed term NaN and NaN the pose index.
      const now = performance.now()
      const elapsed = Math.min(0.25, Math.max(0, (now - prev) / 1000))
      prev = now
      phaseRef.current += elapsed * poseStepsPerSecond(rateRef.current)
      const frame = runnerFrame(phaseRef.current)
      if (frame !== frameRef.current) {
        frameRef.current = frame
        if (canvasRef.current) draw(canvasRef.current, seriesRef.current, scaleRef.current, frame)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [running, theme])

  const latestPrompt = series.prompt[series.prompt.length - 1]
  const latestGen = series.gen[series.gen.length - 1]

  return (
    <div className="bg-surface rounded-lg border border-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-fg-muted">Token Throughput</h3>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-chart-memory rounded inline-block" />
            <span className="text-fg-muted">Prompt:</span>
            {series.length >= 2 && <span className="text-fg-subtle">peak {series.promptPeak.toFixed(1)} t/s</span>}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-chart-compute rounded inline-block" />
            <span className="text-fg-muted">Gen:</span>
            {series.length >= 2 && <span className="text-fg-subtle">peak {series.genPeak.toFixed(1)} t/s</span>}
          </div>
        </div>
      </div>
      <div className="relative h-[160px]">
        <canvas ref={canvasRef} className="w-full h-full" />
      </div>
      {series.length > 0 && (
        <div className="mt-2 text-xs font-mono flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-chart-memory rounded inline-block" />
            <span className="text-fg-muted">Prompt:</span>
            <span className="text-fg-muted">{latestPrompt !== undefined ? `${latestPrompt.toFixed(1)} t/s` : '—'}</span>
            <span className="text-fg-faint">{SMOOTH_LABEL}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-chart-compute rounded inline-block" />
            <span className="text-fg-muted">Gen:</span>
            <span className="text-fg-muted">{latestGen !== undefined ? `${latestGen.toFixed(1)} t/s` : '—'}</span>
            <span className="text-fg-faint">{SMOOTH_LABEL}</span>
          </div>
        </div>
      )}
    </div>
  )
}
