// Pixel-art runner for the throughput chart: frame 0 is standing, frames 1..3 are
// a run cycle walked as 1,2,3,2. Row width is the frame width; every frame is the
// same size so the sprite never jitters between poses.
// Palette: '.' transparent, 'k' ink, 'a' accent.
//
// Rows 0-3 are shared by every frame — a steady head and a scarf that never
// migrates, so only the legs carry the cycle. Each leg ends in a two-cell toe on
// the ground or one row above it, never a single cell in empty air, and the
// frontmost pixel of both stride poses reaches the last column so that he keeps
// touching the tip of the line he is drawn on.

const STAND = [
  '....kk....',
  '...kkkk...',
  '..aakkk...',
  '..a.kk....',
  '...kkkk...',
  '...kkkk...',
  '...kkkk...',
  '...kkkk...',
  '...k..k...',
  '...k..k...',
  '...k..k...',
  '...kk..kk.',
]

const CONTACT = [
  '....kk....',
  '...kkkk...',
  '..aakkk...',
  '..a.kk....',
  '...kkkkk..',
  '...kkkk...',
  '...kkkk...',
  '...kkk....',
  '..kk..kk..',
  '..k....kk.',
  '.kk.....kk',
  '........kk',
]

const PASSING = [
  '....kk....',
  '...kkkk...',
  '..aakkk...',
  '..a.kk....',
  '...kkkk...',
  '...kkkk...',
  '...kkkk...',
  '...kkk....',
  '...kkk....',
  '...k.k....',
  '...k.kk...',
  '...kk.....',
]

const CONTACT_MIRRORED = [
  '....kk....',
  '...kkkk...',
  '..aakkk...',
  '..a.kk....',
  '..kkkkk...',
  '...kkkk...',
  '...kkkk...',
  '....kkk...',
  '..kk..kk..',
  '..k.....kk',
  '..k....kk.',
  '.kk....kk.',
]

export const RUNNER_FRAMES = [STAND, CONTACT, PASSING, CONTACT_MIRRORED]

export const RUNNER_STAND = 0

const RUN_CYCLE = [1, 2, 3, 2]

// One cell of sprite, in canvas pixels. 2 puts him at 20×24 in the 160 px card.
export const RUNNER_PIXEL = 2

// Pose steps per second — one quarter of a full stride cycle, since a cycle is
// four poses. Scaled off the smoothed gen rate so he visibly speeds up with the
// model, and clamped: below the low clamp a slow service looks broken rather than
// leisurely, above the high clamp the cycle smears.
const POSE_STEPS_PER_TOKEN_RATE = 0.08
const MIN_POSE_STEPS_PER_SECOND = 2.5
const MAX_POSE_STEPS_PER_SECOND = 9

export const IDLE_GEN_RATE = 0.5

export function poseStepsPerSecond(genRate) {
  const rate = Number.isFinite(genRate) ? genRate : 0
  return Math.min(
    MAX_POSE_STEPS_PER_SECOND,
    Math.max(MIN_POSE_STEPS_PER_SECOND, rate * POSE_STEPS_PER_TOKEN_RATE),
  )
}

export function runnerFrame(phase) {
  return RUN_CYCLE[Math.floor(phase) % RUN_CYCLE.length]
}

export function frameSize(frame) {
  return { width: frame[0].length, height: frame.length }
}

// Drawn with feet on `feetY`, `left` as his left edge. Both are canvas coordinates
// in CSS pixels; the caller's transform already carries the device-pixel ratio.
export function drawRunner(ctx, frame, left, feetY, colors) {
  const { width, height } = frameSize(frame)
  const top = feetY - height * RUNNER_PIXEL
  ctx.save()
  for (let row = 0; row < height; row++) {
    for (let col = 0; col < width; col++) {
      const cell = frame[row][col]
      if (cell === '.') continue
      ctx.fillStyle = cell === 'a' ? colors.accent : colors.ink
      ctx.fillRect(left + col * RUNNER_PIXEL, top + row * RUNNER_PIXEL, RUNNER_PIXEL, RUNNER_PIXEL)
    }
  }
  ctx.restore()
}

export function runnerCellCount(frame) {
  return frame.reduce((total, row) => total + [...row].filter(c => c !== '.').length, 0)
}
