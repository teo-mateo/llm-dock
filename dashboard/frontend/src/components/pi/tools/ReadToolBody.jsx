import { rangeText } from '../../../utils/piTools/files'
import { isToolError } from '../../../utils/piTools/payload'
import CodeLines from './CodeLines'
import PathHeader from './PathHeader'
import ResultMessage from './ResultMessage'
import ToolChip from './ToolChip'
import ToolImage from './ToolImage'
import ToolMeta from './ToolMeta'

function ReadContent({ tool }) {
  const { images } = tool.view
  if (images.length > 0) {
    return images.map((image, index) => <ToolImage key={index} image={image} />)
  }
  if (isToolError(tool) || tool.view.lines.length === 0) return null
  return <CodeLines lines={tool.view.lines} />
}

export default function ReadToolBody({ tool }) {
  const { item, view } = tool
  const range = rangeText(view)
  return (
    <>
      <ToolMeta item={item}>
        {view.path != null && <PathHeader path={view.path} />}
        {range != null && <ToolChip>{range}</ToolChip>}
      </ToolMeta>
      <ResultMessage tool={tool} when="error" />
      <ReadContent tool={tool} />
    </>
  )
}
