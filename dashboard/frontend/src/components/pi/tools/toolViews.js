import { genericSummary, safeSummary } from '../../../utils/piTools/summary'
import GenericToolBody from './GenericToolBody'

export const GENERIC_VIEW = { parse: null, summary: genericSummary, Body: GenericToolBody }

const TOOL_VIEWS = {}

export function toolEntry(name, views = TOOL_VIEWS) {
  return Object.hasOwn(views, name) ? views[name] : GENERIC_VIEW
}

export function viewFor(tool, views = TOOL_VIEWS) {
  const entry = toolEntry(tool.item.name, views)
  return entry.parse && tool.view == null ? GENERIC_VIEW : entry
}

export function toolSummary(tool, views = TOOL_VIEWS) {
  return safeSummary(viewFor(tool, views).summary, tool)
}
