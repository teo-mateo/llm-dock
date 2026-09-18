import { describe, it, expect } from 'vitest'
import { AXIS_HEADROOM, SCALE_HOLD_SECONDS, SMOOTH_POINTS, advanceScale, niceCeiling, prepareSeries, smoothRate } from './tokenSeries'

function points(values, dt = 0.2) {
  return values.map(generationTokensRate => ({ promptTokensRate: 0, generationTokensRate, dt }))
}

function withSpike(at, value) {
  const history = []
  for (let i = 0; i < 20; i++) {
    history.push({ promptTokensRate: 0, generationTokensRate: i === at ? value : 80, dt: 0.2 })
  }
  return history
}

describe('smoothRate', () => {
  it('averages the trailing window', () => {
    const series = points([110, 50, 110, 50, 110, 50, 110, 50])
    const smoothed = smoothRate(series, 'generationTokensRate')
    expect(SMOOTH_POINTS).toBe(5)
    expect(smoothed[smoothed.length - 1]).toBeCloseTo(74)
    expect(smoothed[smoothed.length - 1]).not.toBe(series[series.length - 1].generationTokensRate)
  })

  it('weights each point by the interval its rate covers', () => {
    const smoothed = smoothRate([
      { generationTokensRate: 100, dt: 1 },
      { generationTokensRate: 10, dt: 0.1 }
    ], 'generationTokensRate')
    // (100×1 + 10×0.1) / 1.1: an unweighted mean answers 55 and lets the short
    // poll outweigh the long one.
    expect(smoothed[1]).toBeCloseTo(91.818, 3)
  })

  it('fills a partial window at the left edge with the points so far', () => {
    const smoothed = smoothRate(points([10, 20, 30]), 'generationTokensRate')
    expect(smoothed[0]).toBe(10)
    expect(smoothed[1]).toBeCloseTo(15)
  })

  it('falls back to a plain mean when no interval is recorded', () => {
    const smoothed = smoothRate([{ generationTokensRate: 20 }, { generationTokensRate: 40 }], 'generationTokensRate')
    expect(smoothed[0]).toBe(20)
    expect(smoothed[1]).toBe(30)
  })

  it('treats a missing rate as idle rather than skipping the point', () => {
    expect(smoothRate([{ dt: 0.2 }, { generationTokensRate: 100, dt: 0.2 }], 'generationTokensRate')[1])
      .toBeCloseTo(50)
  })

  it('keeps a flat series flat', () => {
    for (const value of smoothRate(points([75, 75, 75, 75, 75, 75]), 'generationTokensRate')) {
      expect(value).toBeCloseTo(75, 6)
    }
  })
})

describe('niceCeiling', () => {
  it('leaves an already-nice ceiling alone', () => {
    for (const value of [40, 80, 240, 400]) expect(niceCeiling(value)).toBe(value)
  })

  it('rounds up, never down', () => {
    for (const value of [5, 41, 137, 216, 999, 4321]) {
      expect(niceCeiling(value)).toBeGreaterThanOrEqual(value)
    }
  })

  it('lands every gridline on an integer, not just the top one', () => {
    for (const value of [5, 41, 137, 216, 999, 4321]) {
      const quarter = niceCeiling(value) / 4
      expect(Number.isInteger(quarter)).toBe(true)
    }
  })

  it('picks the next step up rather than the next decade', () => {
    expect(niceCeiling(216)).toBe(240)
    expect(niceCeiling(41)).toBe(80)
  })

  it('floors an idle axis at four', () => {
    expect(niceCeiling(0)).toBe(4)
    expect(niceCeiling(1)).toBe(4)
    expect(niceCeiling(-5)).toBe(4)
  })
})

describe('advanceScale', () => {
  it('adopts the first ceiling it is offered', () => {
    expect(advanceScale({ scale: null, raisedAt: 0 }, 240, 100)).toEqual({ scale: 240, raisedAt: 100 })
  })

  it('rises the moment the data asks for it', () => {
    expect(advanceScale({ scale: 240, raisedAt: 100 }, 400, 120)).toEqual({ scale: 400, raisedAt: 120 })
  })

  it('keeps a raised axis through a lull', () => {
    const held = { scale: 400, raisedAt: 120 }
    expect(advanceScale(held, 80, 120 + SCALE_HOLD_SECONDS - 1)).toBe(held)
  })

  it('releases the hold once it expires', () => {
    expect(advanceScale({ scale: 400, raisedAt: 120 }, 80, 120 + SCALE_HOLD_SECONDS))
      .toEqual({ scale: 80, raisedAt: 120 + SCALE_HOLD_SECONDS })
  })

  it('counts the hold from the last rise, not the last lull', () => {
    const risen = advanceScale({ scale: 400, raisedAt: 100 }, 800, 130)
    expect(risen).toEqual({ scale: 800, raisedAt: 130 })
    expect(advanceScale(risen, 80, 138).scale).toBe(800)
    expect(advanceScale(risen, 80, 140).scale).toBe(80)
  })

  it('does not re-arm the hold on an unchanged candidate', () => {
    const held = { scale: 400, raisedAt: 100 }
    expect(advanceScale(held, 400, 200)).toBe(held)
    // The burst is still the visible peak at T+10s and still is at T+20s; once it
    // ages out the fall must be immediate, not a second hold away.
    expect(advanceScale(held, 80, 200)).toEqual({ scale: 80, raisedAt: 200 })
  })

  it('holds for ten seconds', () => {
    expect(SCALE_HOLD_SECONDS).toBe(10)
  })
})

describe('prepareSeries', () => {
  it('keeps the raw series for the underlay', () => {
    expect(Math.max(...prepareSeries(withSpike(9, 400)).genRaw)).toBe(400)
  })

  it('scales the axis off the smoothed series so one spike cannot flatten the line', () => {
    const { genPeak, genCeiling } = prepareSeries(withSpike(9, 400))
    expect(genPeak).toBeCloseTo(144)
    expect(genCeiling).toBe(240)
    expect(genCeiling).toBeLessThan(400)
  })

  it('lifts the axis above the peak it describes', () => {
    const { genPeak, genCeiling } = prepareSeries(withSpike(9, 400))
    expect(genCeiling).toBeGreaterThan(genPeak * AXIS_HEADROOM - 1)
    expect(AXIS_HEADROOM).toBe(1.5)
  })

  it('reports a peak for a two-point series and guards the empty one', () => {
    const { genPeak, genCeiling } = prepareSeries(points([10, 20]))
    expect(genPeak).toBeCloseTo(15)
    expect(genCeiling).toBe(24)
    expect(prepareSeries([]).genCeiling).toBe(4)
    expect(prepareSeries([]).genPeak).toBe(0)
    expect(prepareSeries([]).length).toBe(0)
  })

  it('keeps a usable axis while the service is idle', () => {
    expect(prepareSeries(points([0, 0, 0])).genCeiling).toBe(4)
  })
})
