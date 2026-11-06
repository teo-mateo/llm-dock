import { describe, it, expect } from 'vitest'
import { answerLabel, needsAnswer, pendingCount, promptOutcome } from './piPrompts'

function session(overrides = {}) {
  return { session_id: 's1', instance_id: 'i1', live: true, prompts: [], ...overrides }
}

describe('needsAnswer', () => {
  it('counts only live sessions with an open prompt', () => {
    expect(needsAnswer(session({ prompts: [{ prompt_id: 'a' }] }))).toBe(true)
    expect(needsAnswer(session({ prompts: [] }))).toBe(false)
    expect(needsAnswer(session({ prompts: null }))).toBe(false)
    expect(needsAnswer(session({ live: false, prompts: [{ prompt_id: 'a' }] }))).toBe(false)
  })

  it('counts the sessions that need an answer', () => {
    const asking = session({ prompts: [{ prompt_id: 'a' }, { prompt_id: 'b' }] })
    expect(pendingCount([asking, session(), session({ live: false })])).toBe(1)
  })

  it('is false for a missing session', () => {
    expect(needsAnswer(undefined)).toBe(false)
  })
})

describe('answerLabel', () => {
  it('reads like the terminal dialog', () => {
    expect(answerLabel(true)).toBe('yes')
    expect(answerLabel(false)).toBe('no')
    expect(answerLabel('red')).toBe('red')
    expect(answerLabel({ choice: 'deny', reason: 'no' })).toBe('deny')
    expect(answerLabel(null)).toBe('nothing')
  })
})

describe('promptOutcome', () => {
  it('treats 200 ok as an accepted answer', () => {
    expect(promptOutcome(200, { ok: true, prompt_id: 'a' })).toEqual({ kind: 'done', message: null })
  })

  it('never reports a 202 as an answered question', () => {
    const outcome = promptOutcome(202, { pending: true })
    expect(outcome.kind).toBe('pending')
    expect(outcome.message).toMatch(/not accepted/i)
  })

  it('names the winner of a 409', () => {
    const outcome = promptOutcome(409, {
      error: 'prompt_already_answered', value: 'green', answered_by: 'terminal', reason: 'answered',
    })
    expect(outcome.kind).toBe('closed')
    expect(outcome.message).toContain('green')
    expect(outcome.message).toContain('terminal')
  })

  it('reports a cancelled or expired question as closed, not answered', () => {
    expect(promptOutcome(409, { error: 'prompt_already_answered', reason: 'cancelled', value: null }).message)
      .toMatch(/cancelled/)
    expect(promptOutcome(409, { error: 'prompt_already_answered', reason: 'expired', value: null }).message)
      .toMatch(/expired/)
  })

  it('distinguishes an offline pi from a lost race', () => {
    expect(promptOutcome(409, { error: 'pi_session_offline' })).toEqual({ kind: 'rejected', message: 'pi is offline' })
  })

  it('maps the remaining failures', () => {
    expect(promptOutcome(404, { error: 'unknown_prompt' }).kind).toBe('closed')
    expect(promptOutcome(400, { error: 'invalid_value' }).message).toMatch(/did not accept/)
    expect(promptOutcome(400, { error: 'invalid_body' }).kind).toBe('rejected')
    expect(promptOutcome(429, {}).kind).toBe('rejected')
    expect(promptOutcome(503, {}).kind).toBe('rejected')
    expect(promptOutcome(418, null).message).toContain('418')
  })
})
