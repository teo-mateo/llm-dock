import { useState } from 'react'
import RawToolBody from './tools/RawToolBody'
import { toolView } from './tools/toolViews'

export default function PiToolDetails({ tool }) {
  const [raw, setRaw] = useState(false)
  const { Body } = toolView(tool.item.name)

  return (
    <div className="flex min-w-0 flex-col gap-2 border-t border-border bg-surface px-3 py-2 max-sm:px-2">
      {raw ? <RawToolBody item={tool.item} /> : <Body tool={tool} />}
      <div className="flex items-center justify-between gap-2">
        {tool.item.truncated ? (
          <p className="m-0 text-xs text-warning-fg">output truncated by pi-remote</p>
        ) : (
          <span />
        )}
        <button
          type="button"
          aria-pressed={raw}
          onClick={() => setRaw((value) => !value)}
          className="shrink-0 text-xs text-fg-subtle hover:text-fg"
        >
          {raw ? 'Formatted ▸' : 'Raw ▸'}
        </button>
      </div>
    </div>
  )
}
