import { splitPath } from '../../../utils/piTools/text'

export default function PathHeader({ path }) {
  const { dir, name } = splitPath(path)
  return (
    <span className="flex min-w-0 font-mono text-xs" title={path}>
      {dir !== '' && <span className="min-w-0 truncate text-fg-muted">{dir}</span>}
      <span className="shrink-0 font-semibold text-fg">{name}</span>
    </span>
  )
}
