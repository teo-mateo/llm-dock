import { isToolError } from './payload'
import { genericSummary } from './summary'
import { splitPath, stringField } from './text'

const HUNK_START = /^@@ -(\d+)(?:,\d+)? \+(\d+)/

function classify(line, inHunk) {
  if (line.startsWith('\\')) return { kind: 'meta', text: line }
  if (line.startsWith('@@')) return { kind: 'hunk', text: line }
  if (!inHunk) return { kind: 'header', text: line }
  if (line.startsWith('+')) return { kind: 'add', text: line.slice(1) }
  if (line.startsWith('-')) return { kind: 'remove', text: line.slice(1) }
  return { kind: 'context', text: line.startsWith(' ') ? line.slice(1) : line }
}

export function parsePatch(patch) {
  if (patch === '') return []
  const out = []
  let inHunk = false
  const rows = patch.replace(/\r/g, '').split('\n')
  if (rows.at(-1) === '') rows.pop()
  for (const line of rows) {
    const parsed = classify(line, inHunk)
    if (parsed.kind === 'hunk') inHunk = true
    out.push(parsed)
  }
  return out
}

export function numberLines(lines) {
  let oldLine = null
  let newLine = null
  return lines.map((line) => {
    if (line.kind === 'hunk') {
      const match = HUNK_START.exec(line.text)
      oldLine = match ? Number(match[1]) : null
      newLine = match ? Number(match[2]) : null
      return { ...line, number: null }
    }
    if (line.kind === 'remove') {
      const number = oldLine
      if (oldLine != null) oldLine += 1
      return { ...line, number }
    }
    if (line.kind === 'add' || line.kind === 'context') {
      const number = newLine
      if (newLine != null) newLine += 1
      if (line.kind === 'context' && oldLine != null) oldLine += 1
      return { ...line, number }
    }
    return { ...line, number: null }
  })
}

export function editStats(lines) {
  let adds = 0
  let removes = 0
  for (const line of lines) {
    if (line.kind === 'add') adds += 1
    else if (line.kind === 'remove') removes += 1
  }
  return { adds, removes }
}

function textLines(value) {
  return typeof value === 'string' ? value.replace(/\r/g, '').split('\n') : []
}

export function fallbackDiff(args) {
  const edits = Array.isArray(args?.edits) ? args.edits : []
  return edits.flatMap((edit, index) => [
    { kind: 'hunk', text: `edit ${index + 1}` },
    ...textLines(edit?.oldText).map((text) => ({ kind: 'remove', text })),
    ...textLines(edit?.newText).map((text) => ({ kind: 'add', text })),
  ])
}

export function parseEdit(args, result) {
  if (args == null) return null
  const patch = stringField(result?.details, 'patch') || null
  const diff = patch != null ? parsePatch(patch) : fallbackDiff(args)
  return {
    path: stringField(args, 'path'),
    hasPatch: patch != null,
    stats: editStats(diff),
    lines: numberLines(diff.filter((line) => line.kind !== 'header' && line.kind !== 'meta')),
  }
}

export function editSummary(tool) {
  const { view } = tool
  if (view?.path == null) return genericSummary(tool)
  const { name } = splitPath(view.path)
  if (isToolError(tool)) return `${name} · failed`
  if (!view.hasPatch) return name
  return `${name} +${view.stats.adds} −${view.stats.removes}`
}
