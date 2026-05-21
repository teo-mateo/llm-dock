import { useState } from 'react'

// Per-conversation main system prompt. The textarea is backed by LOCAL
// state — the previous version bound `value` straight to the persisted
// `conversation.main_system_prompt` prop while `onChange` only fired an
// async server PUT, so every keystroke was re-rendered back to the stale
// prop value and the box looked read-only. Here the edit lives locally
// and is persisted once, on blur.
//
// The parent remounts this component per conversation (key={conversation.id}),
// so local state initializes cleanly from the prop on every conversation
// switch without a useEffect resync.
export default function SystemPromptEditor({ mainPrompt, onSaveMain }) {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState(mainPrompt)
  // Last value known to be persisted. Drives the dirty indicator without
  // depending on the parent reloading the conversation after a save.
  const [savedValue, setSavedValue] = useState(mainPrompt)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const dirty = value !== savedValue

  async function commit() {
    if (!dirty || saving) return
    setSaving(true)
    setError(null)
    try {
      await onSaveMain(value)
      setSavedValue(value)
    } catch (e) {
      setError(e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border-b border-border">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-4 py-2 text-xs text-fg-subtle hover:text-fg-muted w-full text-left"
      >
        <i className={`fa-solid fa-chevron-${open ? 'down' : 'right'} text-[10px]`}></i>
        <i className="fa-solid fa-sliders"></i>
        <span>System Prompt</span>
        {saving && <span className="text-fg-subtle">Saving…</span>}
        {!saving && dirty && <span className="text-warning-fg">Unsaved</span>}
      </button>
      {open && (
        <div className="px-4 pb-3 space-y-1">
          <label className="text-xs text-fg-muted block">Main Model</label>
          <textarea
            value={value}
            onChange={e => setValue(e.target.value)}
            onBlur={commit}
            rows={3}
            className="w-full bg-surface border border-border rounded px-3 py-2 text-xs text-fg resize-none focus:outline-none focus:border-accent"
          />
          <p className="text-[10px] text-fg-subtle">
            Applies to this conversation only. Saved when you click away.
          </p>
          {error && (
            <p className="text-[10px] text-danger-fg">
              <i className="fa-solid fa-triangle-exclamation mr-1"></i>{error}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
