import { describe, it, expect } from 'vitest'
import BashToolBody from './BashToolBody'
import EditToolBody from './EditToolBody'
import GenericToolBody from './GenericToolBody'
import { GENERIC_VIEW, toolEntry, toolSummary, viewFor } from './toolViews'

const Body = () => null
const views = {
  bash: { parse: (args) => (args?.command ? { command: args.command } : null), summary: (tool) => `$ ${tool.view.command}`, Body },
}
const tool = (name, args, view) => ({ item: { name, args: JSON.stringify(args) }, args, result: null, view })

describe('toolViews', () => {
  it('bash and edit have their own viewers', () => {
    expect(toolEntry('bash').Body).toBe(BashToolBody)
    expect(toolEntry('edit').Body).toBe(EditToolBody)
  })

  it('an unknown tool gets the generic view', () => {
    expect(toolEntry('web_search').Body).toBe(GenericToolBody)
    expect(viewFor(tool('web_search', { q: 1 }, null))).toBe(GENERIC_VIEW)
  })

  it('a tool named like an object property is still unknown', () => {
    for (const name of ['toString', 'constructor', '__proto__', 'hasOwnProperty']) {
      expect(toolEntry(name)).toBe(GENERIC_VIEW)
    }
  })

  it('a registered tool with a parsed view gets its own viewer', () => {
    const parsed = tool('bash', { command: 'ls' }, { command: 'ls' })
    expect(viewFor(parsed, views).Body).toBe(Body)
    expect(toolSummary(parsed, views)).toBe('$ ls')
  })

  it('a registered tool whose payload did not parse falls back to generic', () => {
    const unparsed = tool('bash', { cmd: 'ls' }, null)
    expect(viewFor(unparsed, views)).toBe(GENERIC_VIEW)
    expect(toolSummary(unparsed, views)).toBe('cmd=ls')
  })
})
