const MAX_SUMMARY_CHARS = 160

function isQuietAssistant(item) {
  return item.kind === 'assistant' && !item.streaming && item.text.trim() === ''
}

export function groupToolRuns(items) {
  const out = []
  let group = null
  for (const item of items) {
    if (item.kind === 'tool') {
      if (!group) {
        group = { kind: 'tool_group', id: `g${item.id}`, tools: [] }
        out.push(group)
      }
      group.tools.push(item)
    } else if (!(group && isQuietAssistant(item))) {
      group = null
      out.push(item)
    }
  }
  return out
}

function valueText(value) {
  return typeof value === 'string' ? value : JSON.stringify(value)
}

function objectSummary(args) {
  try {
    const parsed = JSON.parse(args)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return Object.entries(parsed)
        .map(([key, value]) => `${key}=${valueText(value)}`)
        .join(' · ')
    }
  } catch {
    return args
  }
  return args
}

export function argsSummary(args) {
  if (args == null) return ''
  const flat = objectSummary(args).replace(/\s+/g, ' ').trim()
  return flat.length > MAX_SUMMARY_CHARS ? `${flat.slice(0, MAX_SUMMARY_CHARS)}…` : flat
}

export function toolStatusText(item) {
  if (item.status === 'running') return 'running…'
  if (item.status === 'error') return 'error'
  if (item.durationMs == null) return 'done'
  return `done · ${(item.durationMs / 1000).toFixed(1)} s`
}
