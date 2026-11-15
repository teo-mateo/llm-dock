import { genericSummary } from './summary'
import { intField, numberText, splitPath, stringField } from './text'

export function parseRead(args, result) {
  if (args == null) return null
  const first = intField(args, 'offset')
  const limit = intField(args, 'limit')
  return {
    path: stringField(args, 'path'),
    first,
    last: first != null && limit != null ? first + limit - 1 : null,
    limit,
    images: result?.images ?? [],
    lines: numberText(result?.text ?? '', first ?? 1),
  }
}

export function rangeText(view) {
  if (view.first != null && view.last != null) return `lines ${view.first}–${view.last}`
  if (view.first != null) return `from line ${view.first}`
  if (view.limit != null) return `first ${view.limit} lines`
  return null
}

export function readSummary(tool) {
  const { view } = tool
  if (view?.path == null) return genericSummary(tool)
  const { name } = splitPath(view.path)
  if (view.images.length > 0) return `${name} · image`
  if (view.first == null) return name
  return `${name} L${view.first}–${view.last ?? ''}`
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
