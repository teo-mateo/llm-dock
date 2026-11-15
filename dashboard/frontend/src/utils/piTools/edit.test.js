import { describe, it, expect } from 'vitest'
import { editStats, editSummary, fallbackDiff, numberLines, parseEdit, parsePatch } from './edit'
import { parseToolCall } from './payload'

const patch = [
  '--- /forgejo/wt/AccountView.cs',
  '+++ /forgejo/wt/AccountView.cs',
  '@@ -1,5 +1,6 @@',
  ' using HeapzillaMail.Api.Attachments;',
  '+using HeapzillaMail.Core.Models;',
  ' ',
  ' namespace HeapzillaMail.Api.Accounts;',
  ' ',
  ' /// <summary>',
].join('\n')

const successResult = JSON.stringify({
  content: [{ type: 'text', text: 'Successfully replaced 1 block(s) in AccountView.cs.' }],
  details: { diff: '1: using', patch, firstChangedLine: 2 },
})
const errorResult = JSON.stringify({ content: [{ type: 'text', text: 'Could not find the exact text.' }], isError: true })
const defaultArgs = '{"path":"/forgejo/wt-hzm-74/frontend/src/api.ts","edits":[{"oldText":"a","newText":"a\\nb"}]}'

function tool(output, status = 'done', args = defaultArgs) {
  const item = { id: 't1', name: 'edit', args, output, status, durationMs: 3, truncated: false }
  return { ...parseToolCall(args, output, parseEdit), item }
}

const kinds = (lines) => lines.map((line) => line.kind)

describe('parsePatch', () => {
  it('parses kinds in order and strips the markers', () => {
    const lines = parsePatch(patch)
    expect(kinds(lines)).toEqual(['header', 'header', 'hunk', 'context', 'add', 'context', 'context', 'context', 'context'])
    expect(lines[3].text).toBe('using HeapzillaMail.Api.Attachments;')
    expect(lines[4].text).toBe('using HeapzillaMail.Core.Models;')
    expect(lines[5].text).toBe('')
    expect(editStats(lines)).toEqual({ adds: 1, removes: 0 })
  })

  it('a trailing newline adds no line', () => {
    const lines = numberLines(parsePatch('@@ -1 +1 @@\n-old\n+new\n'))
    expect(kinds(lines)).toEqual(['hunk', 'remove', 'add'])
    expect(numberLines(parsePatch('@@ -1,2 +1,2 @@\n a\n \n')).map((line) => line.number)).toEqual([null, 1, 2])
  })

  it('an empty patch has no lines', () => {
    expect(parsePatch('')).toEqual([])
  })

  it('classifies marker-prefixed content inside a hunk', () => {
    const lines = parsePatch('--- a/notes\n+++ b/notes\n@@ -1,4 +1,4 @@\n--- stays in JMAP;\n+++ added plus line\n context')
    expect(lines[3]).toEqual({ kind: 'remove', text: '-- stays in JMAP;' })
    expect(lines[4]).toEqual({ kind: 'add', text: '++ added plus line' })
    expect(editStats(lines)).toEqual({ adds: 1, removes: 1 })
  })

  it('the no-newline marker is meta and does not count', () => {
    const lines = parsePatch('--- a/notes\n+++ b/notes\n@@ -1,2 +1,2 @@\n context\n\\ No newline at end of file')
    expect(lines.at(-1).kind).toBe('meta')
    expect(editStats(lines)).toEqual({ adds: 0, removes: 0 })
  })

  it('handles carriage returns', () => {
    const lines = parsePatch('--- a/x\r\n+++ b/x\r\n@@ -1,2 +1,2 @@\r\n-old\r\n+new')
    expect(kinds(lines)).toEqual(['header', 'header', 'hunk', 'remove', 'add'])
    expect(lines[3].text).toBe('old')
    expect(lines[4].text).toBe('new')
  })

  it('keeps every hunk header', () => {
    const lines = parsePatch('--- a/x\n+++ b/x\n@@ -1,2 +1,2 @@\n-one\n+two\n@@ -10,2 +10,2 @@\n-three\n+four')
    expect(kinds(lines)).toEqual(['header', 'header', 'hunk', 'remove', 'add', 'hunk', 'remove', 'add'])
    expect(lines[5].text).toBe('@@ -10,2 +10,2 @@')
    expect(editStats(lines)).toEqual({ adds: 2, removes: 2 })
  })
})

describe('numberLines', () => {
  it('numbers removed lines from the old side and the rest from the new side', () => {
    const lines = numberLines(parsePatch('@@ -18,4 +18,5 @@\n a\n-b\n-c\n+d\n+e\n+f\n g\n@@ -40 +41 @@\n h'))
    expect(lines.map((line) => line.number)).toEqual([null, 18, 19, 20, 19, 20, 21, 22, null, 41])
  })

  it('leaves the fallback hunks unnumbered', () => {
    expect(numberLines(fallbackDiff({ edits: [{ oldText: 'x', newText: 'y' }] })).map((line) => line.number)).toEqual([
      null,
      null,
      null,
    ])
  })
})

describe('fallbackDiff', () => {
  it('renders each edit block', () => {
    const lines = fallbackDiff({ edits: [{ oldText: 'a\nb', newText: 'a\nb\nc' }, { oldText: 'x', newText: 'y' }] })
    expect(lines.map((line) => [line.kind, line.text])).toEqual([
      ['hunk', 'edit 1'],
      ['remove', 'a'],
      ['remove', 'b'],
      ['add', 'a'],
      ['add', 'b'],
      ['add', 'c'],
      ['hunk', 'edit 2'],
      ['remove', 'x'],
      ['add', 'y'],
    ])
  })

  it('tolerates a missing edits list', () => {
    expect(fallbackDiff({ path: '/a/b/c.kt' })).toEqual([])
    expect(fallbackDiff(null)).toEqual([])
  })
})

describe('parseEdit', () => {
  it('drops headers and meta lines from the body', () => {
    const { view } = tool(successResult)
    expect(view.hasPatch).toBe(true)
    expect(kinds(view.lines)[0]).toBe('hunk')
    expect(view.stats).toEqual({ adds: 1, removes: 0 })
  })

  it('falls back to the edits without a patch', () => {
    const { view } = tool(null, 'running')
    expect(view.hasPatch).toBe(false)
    expect(kinds(view.lines)).toEqual(['hunk', 'remove', 'add', 'add'])
  })
})

describe('editSummary', () => {
  it('shows the file name with counts, failed, or the name alone', () => {
    expect(editSummary(tool(successResult))).toBe('api.ts +1 −0')
    expect(editSummary(tool(errorResult, 'error'))).toBe('api.ts · failed')
    expect(editSummary(tool(null, 'running'))).toBe('api.ts')
  })

  it('a result flagged isError counts as failed', () => {
    const output = JSON.stringify({ content: [{ type: 'text', text: 'no' }], details: { patch }, isError: true })
    expect(editSummary(tool(output))).toBe('api.ts · failed')
  })

  it('falls back to the args when there is no path', () => {
    expect(editSummary(tool(null, 'done', '{"foo":"bar"}'))).toBe('foo=bar')
  })
})
