import CodeLines from './CodeLines'
import PathHeader from './PathHeader'
import ResultMessage from './ResultMessage'
import ToolChip from './ToolChip'
import ToolMeta from './ToolMeta'

export default function WriteToolBody({ tool }) {
  const { item, view } = tool
  return (
    <>
      <ToolMeta item={item}>
        {view.path != null && <PathHeader path={view.path} />}
        <ToolChip>{view.lines.length} lines</ToolChip>
      </ToolMeta>
      <ResultMessage tool={tool} when="error" />
      {view.lines.length > 0 && <CodeLines lines={view.lines} />}
      <ResultMessage tool={tool} when="success" />
    </>
  )
}
