import { describe, it, expect } from 'vitest'
import { isReasoningLevelRejection } from './levelRejection'

function withCode(code) {
  const err = new Error('boom')
  if (code) err.code = code
  return err
}

describe('isReasoningLevelRejection', () => {
  it('matches the server code for a level the service does not offer', () => {
    // Literal, not the production constant: the server pins this exact string
    // (dashboard/tests/test_chat_reasoning_levels.py), and a rename that broke
    // the contract must fail here, not move both sides together.
    expect(isReasoningLevelRejection(withCode('invalid_reasoning_level'))).toBe(true)
  })

  // The retry in ChatPage creates the conversation a second time, so it must
  // fire on the level rejection alone: a 500 or a 401 can arrive after the
  // first create already succeeded.
  it('rejects every other failure, including one whose prose mentions the level', () => {
    const prose = new Error("reasoning_level 'xhigh' is not offered by service 'vllm-a'")
    expect(isReasoningLevelRejection(prose)).toBe(false)
    expect(isReasoningLevelRejection(withCode('revision_conflict'))).toBe(false)
    expect(isReasoningLevelRejection(withCode(null))).toBe(false)
    expect(isReasoningLevelRejection(undefined)).toBe(false)
  })
})
