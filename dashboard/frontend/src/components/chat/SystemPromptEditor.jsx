import { useState } from 'react'

export default function SystemPromptEditor({ mainPrompt, sidekickPrompt, onChangeMain, onChangeSidekick }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border-b border-border">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-4 py-2 text-xs text-fg-subtle hover:text-fg-muted w-full text-left"
      >
        <i className={`fa-solid fa-chevron-${open ? 'down' : 'right'} text-[10px]`}></i>
        <i className="fa-solid fa-sliders"></i>
        <span>System Prompts</span>
      </button>
      {open && (
        <div className="px-4 pb-3 space-y-3">
          <div>
            <label className="text-xs text-fg-muted mb-1 block">Main Model</label>
            <textarea
              value={mainPrompt}
              onChange={e => onChangeMain(e.target.value)}
              rows={3}
              className="w-full bg-surface border border-border rounded px-3 py-2 text-xs text-fg resize-none focus:outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="text-xs text-fg-muted mb-1 block">Critic Model</label>
            <textarea
              value={sidekickPrompt}
              onChange={e => onChangeSidekick(e.target.value)}
              rows={3}
              className="w-full bg-surface border border-border rounded px-3 py-2 text-xs text-fg resize-none focus:outline-none focus:border-accent"
            />
          </div>
        </div>
      )}
    </div>
  )
}
