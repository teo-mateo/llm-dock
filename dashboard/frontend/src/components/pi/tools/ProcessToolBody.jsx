import { processOutput, processStatusTone } from '../../../utils/piTools/process'
import CappedText from './CappedText'
import KeyValueGrid from './KeyValueGrid'
import ResultMessage from './ResultMessage'
import ToolChip from './ToolChip'
import ToolMeta from './ToolMeta'

function detailEntries(view) {
  return [
    ['command', view.command],
    ['cwd', view.cwd],
    ['id', view.id],
    ['exit code', view.exitCode == null ? null : String(view.exitCode)],
  ].filter(([, value]) => value != null && value !== '')
}

export default function ProcessToolBody({ tool }) {
  const { item, view } = tool
  const entries = detailEntries(view)
  const output = processOutput(tool)
  return (
    <>
      <ToolMeta item={item}>
        <span className="font-semibold text-fg">{view.action ?? 'process'}</span>
        {view.status && <ToolChip tone={processStatusTone(view.status, view.exitCode)}>{view.status}</ToolChip>}
        {view.name && <span className="text-fg-muted">{view.name}</span>}
        {view.pid != null && <span className="font-mono text-fg-muted">pid {view.pid}</span>}
      </ToolMeta>
      {entries.length > 0 && <KeyValueGrid entries={entries} />}
      <ResultMessage tool={tool} when="error" />
      {output !== '' && <CappedText text={output} wrap={false} />}
    </>
  )
}
