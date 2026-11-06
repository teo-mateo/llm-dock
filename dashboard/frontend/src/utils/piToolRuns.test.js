import { describe, it, expect } from 'vitest'
import { argsSummary, groupToolRuns, moreLabel, toolStatusText, visibleTools } from './piToolRuns'

const tool = (id) => ({ kind: 'tool', id: `t${id}`, status: 'done' })
const assistant = (id, text, streaming = false) => ({ kind: 'assistant', id: `a${id}`, text, streaming })
const user = (id) => ({ kind: 'user', id: `u${id}`, text: 'hi' })

describe('groupToolRuns', () => {
  it('groups consecutive tools into one block', () => {
    const out = groupToolRuns([user(1), tool(1), tool(2), assistant(1, 'done')])
    expect(out.map((item) => item.kind)).toEqual(['user', 'tool_group', 'assistant'])
    expect(out[1].tools.map((item) => item.id)).toEqual(['t1', 't2'])
    expect(out[1].id).toBe('gt1')
  })

  it('absorbs empty assistant turns between tools', () => {
    const out = groupToolRuns([tool(1), assistant(1, '  '), tool(2), assistant(2, 'answer')])
    expect(out).toHaveLength(2)
    expect(out[0].tools).toHaveLength(2)
    expect(out[1].text).toBe('answer')
  })

  it('assistant text splits groups', () => {
    const out = groupToolRuns([tool(1), assistant(1, 'looking'), tool(2)])
    expect(out.map((item) => item.kind)).toEqual(['tool_group', 'assistant', 'tool_group'])
  })

  it('streaming assistant is not absorbed', () => {
    const out = groupToolRuns([tool(1), assistant(1, '', true)])
    expect(out.map((item) => item.kind)).toEqual(['tool_group', 'assistant'])
  })

  it('empty assistant before the first tool stays', () => {
    const out = groupToolRuns([assistant(1, ''), tool(1)])
    expect(out.map((item) => item.kind)).toEqual(['assistant', 'tool_group'])
  })
})

describe('argsSummary', () => {
  it('json object becomes key=value pairs', () => {
    expect(argsSummary('{"account":"me","limit":5,"flags":["a"]}')).toBe('account=me · limit=5 · flags=["a"]')
  })

  it('non-json and truncated json stay raw, flattened', () => {
    expect(argsSummary('{"command":"ls\n -la')).toBe('{"command":"ls -la')
  })

  it('null is empty and long text is cut', () => {
    expect(argsSummary(null)).toBe('')
    expect(argsSummary('x'.repeat(200))).toHaveLength(161)
  })
})

describe('toolStatusText', () => {
  it('describes each status', () => {
    expect(toolStatusText({ status: 'running' })).toBe('running…')
    expect(toolStatusText({ status: 'error' })).toBe('error')
    expect(toolStatusText({ status: 'done', durationMs: 1400 })).toBe('done · 1.4 s')
    expect(toolStatusText({ status: 'done', durationMs: null })).toBe('done')
  })
})

describe('visibleTools', () => {
  const tools = [tool(1), tool(2), tool(3), tool(4), tool(5)]

  it('three or fewer are all shown', () => {
    expect(visibleTools(tools.slice(0, 3), false)).toEqual({ shown: tools.slice(0, 3), hidden: 0 })
  })

  it('more than three shows the first three and counts the rest', () => {
    expect(visibleTools(tools, false)).toEqual({ shown: tools.slice(0, 3), hidden: 2 })
    expect(moreLabel(2)).toBe('2 more…')
  })

  it('expanded shows all', () => {
    expect(visibleTools(tools, true)).toEqual({ shown: tools, hidden: 0 })
  })
})
