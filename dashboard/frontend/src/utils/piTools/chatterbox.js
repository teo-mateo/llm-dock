import { genericSummary } from './summary'
import { arrayField, boolField, firstCollapsedLine, intField, isPlainObject, stringField } from './text'

export function sendTarget(args) {
  const to = stringField(args, 'to')
  switch (stringField(args, 'audience')) {
    case 'participant':
    case 'private':
      return to ? `→ ${to}` : ''
    case 'channel':
      return '→ channel'
    default:
      return ''
  }
}

export function parseSend(args, result) {
  if (args == null) return null
  return {
    target: sendTarget(args),
    text: stringField(args, 'text') ?? '',
    private: stringField(args, 'audience') === 'private',
    outcome: stringField(result?.details, 'outcome'),
  }
}

export function sendOutcomeTone(outcome) {
  return outcome === 'confirmed' ? 'success' : 'warning'
}

export function sendSummary(tool) {
  const { view } = tool
  if (view == null || view.target === '' || view.text === '') return genericSummary(tool)
  const target = view.private ? `${view.target} (private)` : view.target
  let text = `${target}: ${firstCollapsedLine(view.text)}`
  if (view.outcome != null && view.outcome !== 'confirmed') text += ` · ${view.outcome}`
  return text
}

export function chatTime(iso) {
  if (iso == null) return ''
  const start = iso.indexOf('T')
  if (start < 0 || iso.length < start + 6) return iso
  return iso.slice(start + 1, start + 6)
}

function chatLine(entry) {
  if (!isPlainObject(entry)) return null
  return {
    time: chatTime(stringField(entry, 'time')),
    from: stringField(entry, 'from') ?? '',
    bot: stringField(entry, 'kind') === 'bot',
    text: stringField(entry, 'text') ?? '',
    important: boolField(entry, 'important'),
    private: boolField(entry, 'private'),
    toYou: boolField(entry, 'addressed'),
  }
}

function person(entry) {
  const nick = stringField(entry, 'nick')
  return nick == null ? null : { nick, bot: stringField(entry, 'kind') === 'bot' }
}

function present(entries, map) {
  return entries == null ? null : entries.map(map).filter((value) => value != null)
}

export function parseLook(args, result) {
  const details = result?.details ?? null
  const view = {
    what: stringField(args, 'what'),
    count: intField(args, 'count'),
    lines: present(arrayField(details, 'items'), chatLine),
    people: present(arrayField(details, 'people'), person),
  }
  return view.what == null && view.lines == null && view.people == null ? null : view
}

export function lookSummary(tool) {
  const what = tool.view?.what
  if (what == null) return genericSummary(tool)
  return tool.view.count != null ? `look ${what} · ${tool.view.count}` : `look ${what}`
}

export function joinSummary(tool) {
  const channel = stringField(tool.args, 'channel')
  return channel ? `join ${channel}` : 'join'
}

export function leaveSummary() {
  return 'leave'
}
