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

  it('abandons when the user has navigated to a different conversation', () => {
    // codex iter 3 P1: a late getConversation resolving for C must not
    // trigger a background send once the route is B.
    expect(pendingFlushDecision(pending, 'B', { id: 'C' }, false)).toBe('abandon')
  })

  it('waits (not abandon) while convId is null between ref-set and navigate commit', () => {
    // Bug behind #46 not fixing /new-chat-issue: handleCreateAndSend sets
    // pendingMsgRef.current synchronously then calls navigate(); a render
    // can fire with convId still null (route hasn't committed yet) and
    // pendingMsgRef already set. Treating that as 'abandon' would clear
    // the queued message before the route settles and the POST never
    // fires.
    expect(pendingFlushDecision(pending, null, null, false)).toBe('wait')
    expect(pendingFlushDecision(pending, null, { id: 'C' }, false)).toBe('wait')
  })
})
