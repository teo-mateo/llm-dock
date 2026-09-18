import { describe, it, expect } from 'vitest'
import {
  IDLE_GEN_RATE,
  RUNNER_FRAMES,
  RUNNER_PIXEL,
  RUNNER_STAND,
  drawRunner,
  frameSize,
  runnerCellCount,
  runnerFrame,
  poseStepsPerSecond,
} from './runnerSprite'

function fakeCtx() {
  const ctx = {
    fillStyle: '',
    saves: 0,
    restores: 0,
    rects: [],
    save() { ctx.saves += 1 },
    restore() { ctx.restores += 1 },
    fillRect(x, y, w, h) { ctx.rects.push({ style: ctx.fillStyle, x, y, w, h }) },
  }
  return ctx
}

describe('RUNNER_FRAMES', () => {
  it('keeps every frame the same size so poses cannot jitter', () => {
    const sizes = RUNNER_FRAMES.map(frameSize)
    for (const size of sizes) expect(size).toEqual(sizes[0])
  })

  it('uses only the palette', () => {
    for (const frame of RUNNER_FRAMES) {
      for (const row of frame) {
        for (const cell of row) expect(['.', 'k', 'a']).toContain(cell)
      }
    }
  })

  it('gives the run cycle three distinct poses, none of them standing', () => {
    const poses = [1, 2, 3].map(index => RUNNER_FRAMES[index].join('|'))
    expect(new Set(poses).size).toBe(3)
    expect(poses).not.toContain(RUNNER_FRAMES[RUNNER_STAND].join('|'))
  })

  it('draws a sprite with enough cells to read at two pixels', () => {
    for (const frame of RUNNER_FRAMES) {
      const cells = runnerCellCount(frame)
      expect(cells).toBeGreaterThan(15)
      expect(cells).toBeLessThan(80)
    }
  })
})

describe('runnerFrame', () => {
  it('walks the run cycle and never stands', () => {
    const walked = Array.from({ length: 8 }, (_, i) => runnerFrame(i))
    expect(walked).toEqual([1, 2, 3, 2, 1, 2, 3, 2])
  })

  it('advances one pose per whole phase', () => {
    expect(runnerFrame(1.9)).toBe(runnerFrame(1.1))
    expect(runnerFrame(2)).not.toBe(runnerFrame(1.9))
  })
})

describe('poseStepsPerSecond', () => {
  it('speeds up with the model', () => {
    expect(poseStepsPerSecond(200)).toBeGreaterThan(poseStepsPerSecond(40))
    expect(poseStepsPerSecond(80)).toBeCloseTo(6.4)
  })

  it('stays inside a strideable band', () => {
    expect(poseStepsPerSecond(0)).toBe(2.5)
    expect(poseStepsPerSecond(1e6)).toBe(9)
  })

  it('survives a rate that is not a number', () => {
    expect(poseStepsPerSecond(undefined)).toBe(2.5)
    expect(poseStepsPerSecond(NaN)).toBe(2.5)
  })

  it('only animates above the idle threshold', () => {
    expect(IDLE_GEN_RATE).toBeGreaterThan(0)
  })
})

describe('frame construction', () => {
  it('keeps the head and scarf identical in every pose', () => {
    const head = RUNNER_FRAMES[0].slice(0, 4).join('|')
    for (const frame of RUNNER_FRAMES) expect(frame.slice(0, 4).join('|')).toBe(head)
  })

  it('grounds a foot toward the front of both stride poses', () => {
    // He is placed flush with the plot edge, so a bounding box that touches the
    // edge is not a foot that touches the line: the frontmost pixel has to be one
    // he is standing on, and his toe has to reach the front half of the frame.
    for (const index of [1, 3]) {
      expect(RUNNER_FRAMES[index].some(row => row[9] !== '.')).toBe(true)
      expect([...RUNNER_FRAMES[index][11]].slice(5).some(c => c !== '.')).toBe(true)
    }
  })

  it('keeps every frame standing on at least one foot', () => {
    for (const frame of RUNNER_FRAMES) {
      expect(frame[frame.length - 1].includes('k')).toBe(true)
    }
  })

  it('keeps the idle pose distinct from the in-between pose', () => {
    expect(RUNNER_FRAMES[RUNNER_STAND].join('|')).not.toBe(RUNNER_FRAMES[2].join('|'))
  })
})

describe('drawRunner', () => {
  const colors = { ink: '#eeeeee', accent: '#22c55e' }

  it('paints exactly one square per drawn cell', () => {
    const ctx = fakeCtx()
    drawRunner(ctx, RUNNER_FRAMES[RUNNER_STAND], 100, 120, colors)
    expect(ctx.rects).toHaveLength(runnerCellCount(RUNNER_FRAMES[RUNNER_STAND]))
    for (const rect of ctx.rects) {
      expect(rect.w).toBe(RUNNER_PIXEL)
      expect(rect.h).toBe(RUNNER_PIXEL)
      expect([colors.ink, colors.accent]).toContain(rect.style)
    }
  })

  it('stands with his feet on the line', () => {
    const ctx = fakeCtx()
    drawRunner(ctx, RUNNER_FRAMES[RUNNER_STAND], 100, 120, colors)
    const lowest = Math.max(...ctx.rects.map(r => r.y + r.h))
    expect(lowest).toBe(120)
    expect(Math.min(...ctx.rects.map(r => r.y))).toBe(120 - frameSize(RUNNER_FRAMES[RUNNER_STAND]).height * RUNNER_PIXEL)
  })

  it('leaves the context as it found it', () => {
    const ctx = fakeCtx()
    drawRunner(ctx, RUNNER_FRAMES[1], 10, 40, colors)
    expect(ctx.saves).toBe(1)
    expect(ctx.restores).toBe(1)
  })
})
