import { forwardRef, useImperativeHandle, useRef, useState } from 'react'

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
//
// Exposes an imperative `flush()` so the parent can guarantee the latest
// edit is fully persisted before it sends a message — otherwise the
// backend would generate the reply with the stale prompt.
const SystemPromptEditor = forwardRef(function SystemPromptEditor(
  { mainPrompt, onSaveMain },
  ref,
) {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState(mainPrompt)
  // Last value known to be persisted. Drives the dirty indicator without
  // depending on the parent reloading the conversation after a save.
  const [savedValue, setSavedValue] = useState(mainPrompt)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  // Refs mirror the two values so the async commit loop and flush() can
  // read the latest state after an await without a stale closure.
  const valueRef = useRef(mainPrompt)
  const savedValueRef = useRef(mainPrompt)
  // The in-flight commit loop's promise, or null when idle.
  const commitRunningRef = useRef(null)

  const dirty = value !== savedValue

  function handleChange(next) {
    setValue(next)
    valueRef.current = next
  }

  // Persist the textarea to the server. Idempotent while running: a second
  // call returns the in-flight promise. The loop re-reads `valueRef` after
  // every request, so an edit made mid-save (whose blur was swallowed
  // because a save was already running) is still persisted.
  function commit() {
    if (commitRunningRef.current) return commitRunningRef.current
    if (valueRef.current === savedValueRef.current) return null
    const run = (async () => {
      setSaving(true)
      setError(null)
      try {
        while (valueRef.current !== savedValueRef.current) {
          const snapshot = valueRef.current
          await onSaveMain(snapshot)
          savedValueRef.current = snapshot
          setSavedValue(snapshot)
        }
      } catch (e) {
        setError(e.message || 'Save failed')
      } finally {
        setSaving(false)
        commitRunningRef.current = null
      }
    })()
    commitRunningRef.current = run
    return run
  }

  // Resolve once the textarea is fully persisted: kick off a save if the
  // value is dirty, then wait out the (possibly looping) commit. Used by
  // the parent to gate message sends on the prompt being saved.
  async function flush() {
    commit()
    while (commitRunningRef.current) {
      await commitRunningRef.current
    }
  }

  useImperativeHandle(ref, () => ({ flush }))

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
})

export default SystemPromptEditor
