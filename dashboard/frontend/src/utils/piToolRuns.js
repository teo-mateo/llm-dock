const MAX_SUMMARY_CHARS = 160
export const VISIBLE_TOOL_ROWS = 3

function isSilentAssistant(item) {
  return item.kind === 'assistant' && item.text.trim() === ''
}

export function groupToolRuns(items) {
  const out = []
  let group = null
  for (const item of items) {
    if (item.kind === 'tool') {
      if (!group) {
        group = { kind: 'tool_group', id: `g${item.id}`, tools: [], thinking: false }
        out.push(group)
      }
      group.tools.push(item)
      group.thinking = false
    } else if (group && isSilentAssistant(item)) {
      group.thinking = item.streaming
    } else {
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

export function durationText(ms) {
  if (ms == null || ms <= 0) return ''
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

export function toolStatusText(item) {
  if (item.status === 'running') return 'running…'
  if (item.status === 'error') return 'error'
  const duration = durationText(item.durationMs)
  return duration === '' ? 'done' : `done · ${duration}`
}

export function visibleTools(tools, expanded) {
  if (expanded || tools.length <= VISIBLE_TOOL_ROWS) return { shown: tools, hidden: 0 }
  return { shown: tools.slice(0, VISIBLE_TOOL_ROWS), hidden: tools.length - VISIBLE_TOOL_ROWS }
}

export function moreLabel(hidden) {
  return `${hidden} more…`
}
