import useEngineCatalogue from '../hooks/useEngineCatalogue'

// Colour tokens are theme rendering: Tailwind needs the class names as
// literals, so they cannot come from the server. The label does.
const COLORS = {
  llamacpp: 'bg-badge-llamacpp-bg text-badge-llamacpp-fg',
  ik_llamacpp: 'bg-badge-llamacpp-bg text-badge-llamacpp-fg',
  vllm: 'bg-badge-vllm-bg text-badge-vllm-fg',
  ds4: 'bg-badge-ds4-bg text-badge-ds4-fg',
  tabbyapi: 'bg-badge-exl3-bg text-badge-exl3-fg',
  sglang: 'bg-badge-sglang-bg text-badge-sglang-fg',
  maya: 'bg-badge-maya-bg text-badge-maya-fg',
  ninfer: 'bg-badge-ninfer-bg text-badge-ninfer-fg',
}
const NEUTRAL = 'bg-badge-neutral-bg text-badge-neutral-fg'
const INFRA = 'bg-badge-webui-bg text-badge-webui-fg'

export default function EngineBadge({ templateType, infra = false }) {
  const { byType } = useEngineCatalogue()

  let label
  let classes
  if (infra) {
    label = 'WebUI'
    classes = INFRA
  } else if (!templateType) {
    label = 'Unknown'
    classes = NEUTRAL
  } else {
    label = byType[templateType]?.badge_label || templateType
    classes = COLORS[templateType] || NEUTRAL
  }

  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${classes}`}>
      {label}
    </span>
  )
}
