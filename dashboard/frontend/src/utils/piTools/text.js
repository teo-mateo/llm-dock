export function firstCollapsedLine(text) {
  return (text.split('\n')[0] ?? '').replace(/\s+/g, ' ').trim()
}

export function splitPath(path) {
  const slash = path.lastIndexOf('/')
  if (slash < 0) return { dir: '', name: path }
  return { dir: path.slice(0, slash + 1), name: path.slice(slash + 1) }
}

export function stringField(object, key) {
  const value = object?.[key]
  return typeof value === 'string' ? value : null
}

export function intField(object, key) {
  const value = object?.[key]
  return Number.isInteger(value) ? value : null
}

export function objectField(object, key) {
  const value = object?.[key]
  return value != null && typeof value === 'object' && !Array.isArray(value) ? value : null
}

export function numberText(text, firstLine) {
  if (text === '') return []
  const parts = text.replace(/\r/g, '').split('\n')
  if (parts.length > 1 && parts.at(-1) === '') parts.pop()
  return parts.map((line, index) => ({ number: firstLine + index, text: line }))
}
