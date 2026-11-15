import { isToolError } from '../../../utils/piTools/payload'
import CappedText from './CappedText'
import DiffView from './DiffView'
import PathHeader from './PathHeader'
import ToolChip from './ToolChip'
import ToolMeta from './ToolMeta'

function EditMeta({ tool }) {
  const { item, view } = tool
  return (
    <ToolMeta item={item}>
      {view.path != null && <PathHeader path={view.path} />}
      {view.hasPatch && (
        <>
          <ToolChip tone="success">+{view.stats.adds}</ToolChip>
          <ToolChip tone="danger">−{view.stats.removes}</ToolChip>
        </>
      )}
    </ToolMeta>
  )
}

export default function EditToolBody({ tool }) {
  const { view, result } = tool
  const errorText = isToolError(tool) ? (result?.text ?? '') : ''
  return (
    <>
      <EditMeta tool={tool} />
      {errorText !== '' ? (
        <CappedText text={errorText} tone="error" />
      ) : (
        view.lines.length > 0 && <DiffView lines={view.lines} />
      )}
    </>
  )
}
