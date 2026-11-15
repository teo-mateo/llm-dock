import { isToolError } from './payload'
import { genericSummary } from './summary'
import { firstCollapsedLine, stringField } from './text'

const CD_PREFIX = /^cd[ \t]+(?:"([^"]*)"|'([^']*)'|([^\s;&]+))[ \t]*(?:&&|;)[ \t]*/

export function splitCdPrefix(command) {
  const match = CD_PREFIX.exec(command)
  if (!match) return { dir: null, command }
  return { dir: match[1] ?? match[2] ?? match[3], command: command.slice(match[0].length).trim() }
}

export function bashOutput(result) {
  if (result == null) return null
  return stringField(result.structured, 'output') ?? result.text
}

export function bashExitCode(result) {
  const code = result?.structured?.exit_code
  return Number.isInteger(code) ? code : null
}

export function parseBash(args, result) {
  const command = stringField(args, 'command')
  if (command == null) return null
  const timeout = args.timeout
  return {
    ...splitCdPrefix(command),
    timeout: typeof timeout === 'number' ? timeout : null,
    output: bashOutput(result),
    exitCode: bashExitCode(result),
  }
}

export function bashOutcome(tool) {
  const exitCode = tool.view?.exitCode ?? null
  return {
    exitCode,
    failed: exitCode != null && exitCode !== 0,
    timedOut: isToolError(tool) && (tool.result?.text ?? '').includes('timed out'),
  }
}

export function bashSummary(tool) {
  const { view } = tool
  if (view == null) return genericSummary(tool)
  const outcome = bashOutcome(tool)
  let text = `$ ${firstCollapsedLine(view.command)}`
  if (outcome.failed) text += ` · exit ${outcome.exitCode}`
  if (outcome.timedOut) text += ' · timed out'
  return text
}
