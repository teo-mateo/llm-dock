import { describe, it, expect } from 'vitest'
import { genericSummary, safeSummary } from './summary'

const tool = {
  item: { name: 'web_search', args: '{"query":"a b","count":5}', output: null },
  args: { query: 'a b', count: 5 },
  result: null,
}

describe('safeSummary', () => {
  it('uses the summary a viewer returns', () => {
    expect(safeSummary(() => 'custom', tool)).toBe('custom')
  })

  it('falls back to the args summary when a viewer throws', () => {
    const throws = () => {
      throw new Error('bad payload')
    }
    expect(safeSummary(throws, tool)).toBe('query=a b · count=5')
  })

  it('falls back when a viewer returns no text', () => {
    expect(safeSummary(() => undefined, tool)).toBe('query=a b · count=5')
  })
})

describe('genericSummary', () => {
  it('flattens the args', () => {
    expect(genericSummary(tool)).toBe('query=a b · count=5')
  })
})
