import { useState, useMemo } from 'react'

function truncatePreview(content, maxLen = 120) {
  if (!content) return ''
  const trimmed = content.trim()
  if (trimmed.length <= maxLen) return trimmed
  return trimmed.slice(0, maxLen) + '…'
}

export default function PromptSelector({ prompts, selectedPromptId, onSelect, label = 'System Prompt' }) {
  const [open, setOpen] = useState(false)

  const sorted = useMemo(() => {
    return [...(prompts || [])].sort(
      (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0),
    )
  }, [prompts])

  const selected = selectedPromptId ?? null
  const selectedName =
    selected === null
      ? 'None'
      : (sorted.find(p => p.id === selected)?.name ?? 'Custom')

  const optionBase =
    'flex items-start gap-2 p-2 rounded border cursor-pointer transition-colors'

  return (
    <div className="border-b border-border">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-4 py-2 text-xs text-fg-subtle hover:text-fg-muted w-full text-left"
      >
        <i className={`fa-solid fa-chevron-${open ? 'down' : 'right'} text-[10px]`}></i>
        <i className="fa-solid fa-sliders"></i>
        <span>{label}</span>
        <span className="ml-auto text-fg-muted truncate max-w-[120px] text-right">
          {selectedName}
        </span>
      </button>
      {open && (
        <div className="px-4 pb-3 space-y-1">
          <label className="text-xs text-fg-muted block mb-1">
            Select a prompt
          </label>
          <div className="space-y-1">
            <label
              className={`${optionBase} ${
                selected === null
                  ? 'bg-success-subtle border-success text-success-fg'
                  : 'bg-surface border-border hover:bg-surface-strong'
              }`}
            >
              <input
                type="radio"
                name="system-prompt"
                checked={selected === null}
                onChange={() => onSelect(null)}
                className="mt-0.5"
              />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium">None</div>
                <div className="text-[10px] text-fg-subtle mt-0.5">
                  Use the default (empty) system prompt.
                </div>
              </div>
            </label>
            {sorted.map(prompt => {
              const isActive = selected === prompt.id
              return (
                <label
                  key={prompt.id}
                  className={`${optionBase} ${
                    isActive
                      ? 'bg-success-subtle border-success text-success-fg'
                      : 'bg-surface border-border hover:bg-surface-strong'
                  }`}
                >
                  <input
                    type="radio"
                    name="system-prompt"
                    checked={isActive}
                    onChange={() => onSelect(prompt.id)}
                    className="mt-0.5"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium truncate">
                      {prompt.name}
                    </div>
                    <div
                      className="text-[10px] text-fg-subtle mt-0.5"
                      title={prompt.content}
                    >
                      {truncatePreview(prompt.content)}
                    </div>
                  </div>
                </label>
              )
            })}
          </div>
          <p className="text-[10px] text-fg-subtle">
            Selection applies to this conversation only.
          </p>
        </div>
      )}
    </div>
  )
}
