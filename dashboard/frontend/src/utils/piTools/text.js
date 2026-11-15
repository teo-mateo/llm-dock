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
