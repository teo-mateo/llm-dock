import { describe, it, expect } from 'vitest'
import { isReasoningLevelRejection, INVALID_LEVEL_CODE } from './levelRejection'

function withCode(code) {
  const err = new Error('boom')
  if (code) err.code = code
  return err
}

describe('isReasoningLevelRejection', () => {
  it('matches the server code for a level the service does not offer', () => {
    expect(isReasoningLevelRejection(withCode(INVALID_LEVEL_CODE))).toBe(true)
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
