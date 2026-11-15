import { argsSummary } from '../piToolRuns'

export function genericSummary(tool) {
  return argsSummary(tool.item.args)
}

export function safeSummary(summarize, tool) {
  try {
    const text = summarize(tool)
    return typeof text === 'string' ? text : genericSummary(tool)
  } catch {
    return genericSummary(tool)
  }
}
