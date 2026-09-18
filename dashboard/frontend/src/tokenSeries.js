import { POLL_INTERVAL } from './utils'

// Visible span of the throughput chart. 50 polls at the live cadence ≈ 10 s.
export const MAX_POINTS = 50

// Window the drawn line averages over. A raw point is one integer token counter
// delta over one poll, so it moves in exact 5 t/s steps and a steady generation
// reads as a sawtooth: measured CV 0.44 over 36 s of steady decode on a
// spec-decoding vLLM service, 0.28 at 5 points, 0.20 at 12. Five points is the
// knee — 1 s of window for 0.4 s of group delay.
export const SMOOTH_POINTS = 5

const SMOOTH_SECONDS = (SMOOTH_POINTS * POLL_INTERVAL) / 1000

export const SMOOTH_LABEL = SMOOTH_SECONDS < 1
  ? `${Math.round(SMOOTH_SECONDS * 1000)}ms avg`
  : `${Number.isInteger(SMOOTH_SECONDS) ? SMOOTH_SECONDS : SMOOTH_SECONDS.toFixed(1)}s avg`

// The axis ceiling sits above the smoothed peak rather than on it: the peak point
// then reads as a peak instead of being flattened against the frame, and the raw
// underlay's spikes stay inside the plot. The badges report the peak, not this
// padded scale.
export const AXIS_HEADROOM = 1.5

// A held axis is only useful if its labels are readable, so a ceiling is always
// four times a nice step — every one of the four gridlines then lands on a round
// number, not just the top one.
const NICE_STEPS = [1, 2, 3, 4, 5, 6, 8, 10]
const MIN_CEILING = 4

// How long a gen axis stays raised after snapping up. Below this the line can
// fall back to a tighter axis and re-granify the frame under the reader.
export const SCALE_HOLD_SECONDS = 10

// Smallest nice ceiling at or above `value`. Floors at MIN_CEILING so an idle
// service still gets a 0/1/2/3/4 axis.
export function niceCeiling(value) {
  if (!(value > 0)) return MIN_CEILING
  const rough = value / 4
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const step = NICE_STEPS.find(s => rough <= s * magnitude * (1 + 1e-9)) ?? 10 * magnitude
  return Math.max(MIN_CEILING, step * magnitude * 4)
}

// Rise-only axis for the gen line: snap up to a higher ceiling the moment the
// data asks for one, then refuse to shrink for SCALE_HOLD_SECONDS. Returning the
// state rather than closing over it keeps it a pure function of (state,
// candidate, now). `now` and `raisedAt` are seconds on the same clock.
export function advanceScale(state, candidate, now, holdSeconds = SCALE_HOLD_SECONDS) {
  if (state.scale == null || candidate > state.scale) return { scale: candidate, raisedAt: now }
  // An unchanged candidate must not re-arm the hold, or a burst still inside the
  // visible window would delay the fall by a whole hold after it aged out.
  if (candidate === state.scale) return state
  if (now - state.raisedAt >= holdSeconds) return { scale: candidate, raisedAt: now }
  return state
}

// Windowed throughput: the dt-weighted mean of the last `window` points, which is
// the same thing as "tokens over the window ÷ the window". Weights are
// load-bearing — a point's rate covers exactly its own `dt` seconds, so an
// unweighted mean lets one short, bunched poll move the line as much as a full
// one. The window shrinks at the left edge instead of leaving a gap, because the
// chart is right-anchored. Zero total weight (no recorded dt) falls back to the
// plain mean so a series without intervals still draws rather than NaN.
export function smoothRate(history, key, window = SMOOTH_POINTS) {
  const out = []
  for (let i = 0; i < history.length; i++) {
    const start = Math.max(0, i - window + 1)
    let weighted = 0
    let weight = 0
    let plain = 0
    for (let j = start; j <= i; j++) {
      const value = history[j][key] || 0
      const dt = history[j].dt > 0 ? history[j].dt : 0
      weighted += value * dt
      weight += dt
      plain += value
    }
    out.push(weight > 0 ? weighted / weight : plain / (i - start + 1))
  }
  return out
}

// One derivation behind the canvas, the axis scale and the readout, so the line,
// the "max" badges and the number under the chart cannot disagree about which
// series they describe. The raw pairs feed the underlay and nothing else.
export function prepareSeries(history) {
  const points = history.slice(-MAX_POINTS)
  const prompt = smoothRate(points, 'promptTokensRate')
  const gen = smoothRate(points, 'generationTokensRate')
  const full = points.length >= 2
  const promptPeak = full ? Math.max(...prompt) : 0
  const genPeak = full ? Math.max(...gen) : 0
  return {
    length: points.length,
    prompt,
    gen,
    promptRaw: points.map(p => p.promptTokensRate || 0),
    genRaw: points.map(p => p.generationTokensRate || 0),
    promptPeak,
    genPeak,
    promptCeiling: niceCeiling(promptPeak * AXIS_HEADROOM),
    genCeiling: niceCeiling(genPeak * AXIS_HEADROOM),
  }
}
