import { imageLabel, isToolError } from '../../../utils/piTools/payload'
import CappedText from './CappedText'
import KeyValueGrid from './KeyValueGrid'
import ToolMeta from './ToolMeta'

function ArgsView({ tool }) {
  const entries = tool.args ? Object.entries(tool.args) : []
  if (entries.length > 0) return <KeyValueGrid entries={entries} />
  if (tool.item.args != null && tool.args == null) return <CappedText text={tool.item.args} />
  return null
}

function ResultView({ tool }) {
  const { item, result } = tool
  if (result == null) return null
  const tone = isToolError(tool) ? 'error' : 'muted'
  return (
    <>
      {result.text !== '' ? (
        <CappedText text={result.text} tone={tone} />
      ) : (
        result.images.length === 0 && item.output != null && <CappedText text={item.output} tone={tone} />
      )}
      {result.images.map((image, index) => (
        <span key={index} className="font-mono text-xs text-fg-muted">
          {imageLabel(image)}
        </span>
      ))}
    </>
  )
}

export default function GenericToolBody({ tool }) {
  return (
    <>
      <ToolMeta item={tool.item} />
      <ArgsView tool={tool} />
      <ResultView tool={tool} />
    </>
  )
}
