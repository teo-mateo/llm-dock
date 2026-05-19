import { describe, it, expect } from 'vitest'
import { pendingFlushDecision } from './pendingFlush'

const pending = { convId: 'C', content: 'hi', images: undefined }

describe('pendingFlushDecision', () => {
  it('waits when there is no pending message', () => {
    expect(pendingFlushDecision(null, 'C', { id: 'C' }, false)).toBe('wait')
  })

  it('waits while the pending conversation has not loaded yet', () => {
    expect(pendingFlushDecision(pending, 'C', null, false)).toBe('wait')
    expect(pendingFlushDecision(pending, 'C', { id: 'A' }, false)).toBe('wait')
  })

  it('waits while streaming even if route and conversation match', () => {
    expect(pendingFlushDecision(pending, 'C', { id: 'C' }, true)).toBe('wait')
  })

  it('sends when route + loaded conversation match and not streaming', () => {
    expect(pendingFlushDecision(pending, 'C', { id: 'C' }, false)).toBe('send')
  })

  it('abandons when the user has navigated away from the pending route', () => {
    // codex iter 3 P1: a late getConversation resolving for C must not
    // trigger a background send once the route is B.
    expect(pendingFlushDecision(pending, 'B', { id: 'C' }, false)).toBe('abandon')
    expect(pendingFlushDecision(pending, null, { id: 'C' }, false)).toBe('abandon')
  })
})
