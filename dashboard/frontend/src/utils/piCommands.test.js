import { describe, it, expect } from 'vitest'
import { commandOutcome, runEndLabel } from './piCommands'

describe('commandOutcome', () => {
  it('200 ok true is done', () => {
    expect(commandOutcome(200, { ok: true })).toEqual({
      kind: 'done',
      message: null,
    })
  })

  it('200 ok false is failed', () => {
    expect(commandOutcome(200, { ok: false, error: 'failed' })).toEqual({
      kind: 'failed',
      message: 'pi could not run it (failed)',
    })
  })

  it('202 is pending', () => {
    expect(commandOutcome(202, { pending: true })).toEqual({
      kind: 'pending',
      message: 'Sent — pi will pick it up',
    })
  })

  it('409 is offline', () => {
    expect(commandOutcome(409, { error: 'pi_session_offline' })).toEqual({
      kind: 'rejected',
      message: 'pi is offline',
    })
  })

  it('429 is rate limited', () => {
    expect(commandOutcome(429, { error: 'rate_limited' })).toEqual({
      kind: 'rejected',
      message: 'Too many messages — wait a minute',
    })
  })

  it('503 is busy', () => {
    expect(commandOutcome(503, { error: 'queue_full' })).toEqual({
      kind: 'rejected',
      message: 'The dashboard is busy — try again',
    })
  })

  it('400 invalid text is rejected', () => {
    expect(commandOutcome(400, { error: 'invalid_text' })).toEqual({
      kind: 'rejected',
      message: 'Message is empty or too long',
    })
  })

  it('other status is rejected', () => {
    expect(commandOutcome(500, null)).toEqual({
      kind: 'rejected',
      message: 'Could not send (500)',
    })
  })
})

describe('runEndLabel', () => {
  it('stopped within 30 s', () => {
    expect(runEndLabel('error', 1000, 1000)).toBe('stopped')
    expect(runEndLabel('error', 31000, 1000)).toBe('stopped')
  })

  it('not stopped after 30 s', () => {
    expect(runEndLabel('error', 31001, 1000)).toBe('error')
    expect(runEndLabel('error', 999, 1000)).toBe('error')
  })

  it('plain outcomes without a stop', () => {
    expect(runEndLabel('completed', 1000, null)).toBe('run completed')
    expect(runEndLabel('aborted', 1000, null)).toBe('aborted')
    expect(runEndLabel('error', 1000, null)).toBe('error')
  })
})
