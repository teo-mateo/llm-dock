import { describe, it, expect } from 'vitest'
import { applySessionEventsFrame } from './usePiSessionEvents'

const initial = { events: [], lastSeq: 0, summary: null, lagged: false }
const event = (seq) => ({ seq, type: 'state', ts: seq * 1000, payload: {} })

describe('applySessionEventsFrame', () => {
  it('appends events in order and advances lastSeq', () => {
    const state = applySessionEventsFrame(initial, {
      event: 'events',
      data: { events: [event(2), event(1)] },
    })
    expect(state.events.map((row) => row.seq)).toEqual([1, 2])
    expect(state.lastSeq).toBe(2)
  })

  it('drops events at or below lastSeq', () => {
    const existing = {
      ...initial,
      events: [event(1)],
      lastSeq: 1,
    }
    const state = applySessionEventsFrame(existing, {
      event: 'events',
      data: { events: [event(1), event(2)] },
    })
    expect(state.events.map((row) => row.seq)).toEqual([1, 2])
    expect(state.lastSeq).toBe(2)
  })

  it('session frame sets summary', () => {
    const summary = { session_id: 's1', instance_id: 'i1', live: true }
    const state = applySessionEventsFrame(initial, {
      event: 'session',
      data: summary,
    })
    expect(state.summary).toEqual(summary)
  })

  it('lagged frame sets lagged', () => {
    const state = applySessionEventsFrame(initial, {
      event: 'lagged',
      data: {},
    })
    expect(state.lagged).toBe(true)
  })
})
