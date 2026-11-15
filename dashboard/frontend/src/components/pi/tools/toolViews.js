import { genericSummary, safeSummary } from '../../../utils/piTools/summary'
import { bashSummary, parseBash } from '../../../utils/piTools/bash'
import { editSummary, parseEdit } from '../../../utils/piTools/edit'
import { parseRead, parseWrite, readSummary, writeSummary } from '../../../utils/piTools/files'
import { parseProcess, processSummary } from '../../../utils/piTools/process'
import BashToolBody from './BashToolBody'
import EditToolBody from './EditToolBody'
import GenericToolBody from './GenericToolBody'
import ProcessToolBody from './ProcessToolBody'
import ReadToolBody from './ReadToolBody'
import WriteToolBody from './WriteToolBody'

export const GENERIC_VIEW = { parse: null, summary: genericSummary, Body: GenericToolBody }

const TOOL_VIEWS = {
  bash: { parse: parseBash, summary: bashSummary, Body: BashToolBody },
  edit: { parse: parseEdit, summary: editSummary, Body: EditToolBody },
  read: { parse: parseRead, summary: readSummary, Body: ReadToolBody },
  write: { parse: parseWrite, summary: writeSummary, Body: WriteToolBody },
  process: { parse: parseProcess, summary: processSummary, Body: ProcessToolBody },
}

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
