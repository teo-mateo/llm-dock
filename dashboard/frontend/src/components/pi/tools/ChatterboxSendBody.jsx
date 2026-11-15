import { isToolError } from '../../../utils/piTools/payload'
import { sendOutcomeTone } from '../../../utils/piTools/chatterbox'
import ChatText from './ChatText'
import ResultMessage from './ResultMessage'
import ToolChip from './ToolChip'
import ToolMeta from './ToolMeta'

export default function ChatterboxSendBody({ tool }) {
  const { item, view } = tool
  const unconfirmed = view.outcome !== 'confirmed' && !isToolError(tool)
  return (
    <>
      <ToolMeta item={item}>
        {view.target && <span className="font-semibold text-fg">{view.target}</span>}
        {view.private && <ToolChip>private</ToolChip>}
        {view.outcome && <ToolChip tone={sendOutcomeTone(view.outcome)}>{view.outcome}</ToolChip>}
      </ToolMeta>
      <ResultMessage tool={tool} when="error" />
      {view.text !== '' && <ChatText text={view.text} className="rounded-lg bg-surface-muted px-3 py-2" />}
      {unconfirmed && <ResultMessage tool={tool} when="ok" />}
    </>
  )
}
