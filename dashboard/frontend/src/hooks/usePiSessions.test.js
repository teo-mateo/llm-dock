import { describe, it, expect } from 'vitest'
import { applySessionsFrame } from './usePiSessions'

const summary = (sessionId, instanceId, over = {}) => ({
  session_id: sessionId,
  instance_id: instanceId,
  name: 'probe',
  cwd: '/tmp',
  model: null,
  thinking_level: null,
  first_seen: 1000,
  last_seen: 2000,
  ended_at: null,
  end_reason: null,
  live: true,
  state: 'idle',
  context_percent: null,
  ...over,
})

const stateOf = (frame) => applySessionsFrame({ byKey: {}, order: [] }, frame)
const ordered = (state) => state.order.map((key) => state.byKey[key].session_id)

describe('applySessionsFrame', () => {
  it('snapshot replaces the list', () => {
    const state = stateOf({
      event: 'snapshot',
      data: { sessions: [summary('s1', 'i1'), summary('s2', 'i2')] },
    })
    expect(ordered(state)).toEqual(['s1', 's2'])
    expect(state.order.length).toBe(2)
  })

  it('session frame upserts by key', () => {
    const state = applySessionsFrame(
      stateOf({ event: 'snapshot', data: { sessions: [summary('s1', 'i1')] } }),
      { event: 'session', data: summary('s1', 'i1', { name: 'renamed' }) },
    )
    expect(state.order).toEqual(['s1/i1'])
    expect(state.byKey['s1/i1'].name).toBe('renamed')

    const added = applySessionsFrame(state, {
      event: 'session',
      data: summary('s2', 'i2'),
    })
    expect(added.order.length).toBe(2)
    expect(added.byKey['s2/i2'].session_id).toBe('s2')
  })

  it('orders live first then last_seen desc', () => {
    const state = stateOf({
      event: 'snapshot',
      data: {
        sessions: [
          summary('ended-old', 'i1', { live: false, last_seen: 3000 }),
          summary('live-new', 'i1', { live: true, last_seen: 1000 }),
          summary('ended-new', 'i1', { live: false, last_seen: 5000 }),
        ],
      },
    })
    expect(ordered(state)).toEqual(['live-new', 'ended-new', 'ended-old'])
  })
})
