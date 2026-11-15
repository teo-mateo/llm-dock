import { genericSummary, safeSummary } from '../../../utils/piTools/summary'
import GenericToolBody from './GenericToolBody'

const GENERIC_VIEW = { summary: genericSummary, Body: GenericToolBody }

const TOOL_VIEWS = {}

export function toolView(name) {
  return TOOL_VIEWS[name] ?? GENERIC_VIEW
}

export function toolSummary(tool) {
  return safeSummary(toolView(tool.item.name).summary, tool)
}
