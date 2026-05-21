import { useRef, useState } from 'react'

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
  // Mirrors `value` so the async commit loop can read the latest text
  // after an await without a stale closure.
  const valueRef = useRef(mainPrompt)

  const dirty = value !== savedValue

  function handleChange(next) {
    setValue(next)
    valueRef.current = next
  }

  async function commit() {
    // A blur that lands while a save is already running is a no-op here —
    // the loop below re-reads `valueRef` after each request, so the edit
    // is still persisted without its own blur being honored.
    if (saving) return
    if (valueRef.current === savedValue) return
    setSaving(true)
    setError(null)
    let persisted = savedValue
    try {
      // Persist until what's on disk matches the textarea — covers edits
      // made while an earlier request was in flight.
      while (valueRef.current !== persisted) {
        const snapshot = valueRef.current
        await onSaveMain(snapshot)
        persisted = snapshot
      }
      setSavedValue(persisted)
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
            onChange={e => handleChange(e.target.value)}
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
