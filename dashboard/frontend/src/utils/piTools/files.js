import { genericSummary } from './summary'
import { intField, numberText, splitPath, stringField } from './text'

export function rangeText(offset, limit) {
  if (offset != null && limit != null) return `lines ${offset}–${offset + limit - 1}`
  if (offset != null) return `from line ${offset}`
  if (limit != null) return `first ${limit} lines`
  return null
}

export function parseRead(args, result) {
  if (args == null) return null
  const offset = intField(args, 'offset')
  const limit = intField(args, 'limit')
  return {
    path: stringField(args, 'path'),
    range: rangeText(offset, limit),
    offset,
    limit,
    lines: numberText(result?.text ?? '', offset ?? 1),
  }
}

export function readSummary(tool) {
  const { view } = tool
  if (view?.path == null) return genericSummary(tool)
  const { name } = splitPath(view.path)
  if ((tool.result?.images.length ?? 0) > 0) return `${name} · image`
  if (view.offset != null && view.limit != null) return `${name} L${view.offset}–${view.offset + view.limit - 1}`
  if (view.offset != null) return `${name} L${view.offset}–`
  return name
}

export function parseWrite(args) {
  if (args == null) return null
  return { path: stringField(args, 'path'), lines: numberText(stringField(args, 'content') ?? '', 1) }
}

export function writeSummary(tool) {
  const { view } = tool
  if (view?.path == null) return genericSummary(tool)
  return `${splitPath(view.path).name} · ${view.lines.length} lines`
}
