import { describe, it, expect } from 'vitest'
import GenericToolBody from './GenericToolBody'
import { toolSummary, toolView } from './toolViews'

describe('toolView', () => {
  it('an unknown tool gets the generic view', () => {
    expect(toolView('web_search').Body).toBe(GenericToolBody)
  })

  it('the summary falls back to the flattened args', () => {
    const tool = { item: { name: 'web_search', args: '{"query":"q"}' }, args: { query: 'q' }, result: null }
    expect(toolSummary(tool)).toBe('query=q')
  })
})
