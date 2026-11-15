import { splitCdPrefix } from './shell'
import { isToolError } from './payload'
import { genericSummary } from './summary'
import { firstCollapsedLine, intField, objectField, stringField } from './text'

export function parseProcess(args, result) {
  if (args == null && result == null) return null
  const details = result?.details ?? null
  const info = objectField(details, 'process') ?? objectField(objectField(details, 'result'), 'info')
  return {
    action: stringField(details, 'action') ?? stringField(args, 'action'),
    id: stringField(info, 'id') ?? stringField(details, 'id') ?? stringField(args, 'id'),
    name: stringField(info, 'name') ?? stringField(details, 'processName') ?? stringField(args, 'name'),
    pid: intField(info, 'pid'),
    status: stringField(info, 'status') ?? stringField(details, 'processStatus'),
    exitCode: intField(info, 'exitCode') ?? intField(details, 'exitCode'),
    command: stringField(info, 'command') ?? stringField(args, 'command'),
    cwd: stringField(info, 'cwd') ?? stringField(args, 'cwd'),
  }
}

export function processStatusTone(status, exitCode) {
  if (exitCode != null && exitCode !== 0) return 'danger'
  switch (status?.toLowerCase()) {
    case 'running':
      return 'warning'
    case 'exited':
    case 'success':
      return 'success'
    case 'failed':
    case 'killed':
      return 'danger'
    default:
      return 'neutral'
  }
}

function labelled(word, label) {
  return label ? `${word} ${label}` : word
}

function actionText(view) {
  const label = view.name ?? view.id
  switch (view.action) {
    case 'start': {
      const command = view.command ? firstCollapsedLine(splitCdPrefix(view.command).command) : ''
      return labelled('start', label) + (command ? ` · ${command}` : '')
    }
    case 'stop':
    case 'output':
      return labelled(view.action, label)
    case 'list':
      return 'list'
    default:
      return null
  }
}

export function processSummary(tool) {
  const { view } = tool
  const base = view == null ? null : actionText(view)
  if (base == null) return genericSummary(tool)
  let text = base
  if (view.status) text += ` · ${view.status}`
  if (view.exitCode != null && view.exitCode !== 0) text += ` · exit ${view.exitCode}`
  return text
}

export function processOutput(tool) {
  if (isToolError(tool)) return ''
  return (tool.result?.text ?? '').trimEnd()
}
