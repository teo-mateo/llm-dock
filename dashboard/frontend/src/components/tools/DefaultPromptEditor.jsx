import { useEffect, useState } from 'react'
import useMainSystemPrompt from '../../hooks/useMainSystemPrompt'

// Editor for the global default `main_system_prompt` applied to every NEW
// conversation. Existing conversations keep their own stored copy and are
// untouched by edits here.
export default function DefaultPromptEditor() {
  const { data, loading, error, save, reset } = useMainSystemPrompt()

  const [content, setContent] = useState('')
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)
  const [savedNote, setSavedNote] = useState(null)
  const [confirmingReset, setConfirmingReset] = useState(false)

  // Sync the textarea from the server value whenever it changes — but not
  // while the user has unsaved edits, so a background refresh can't stomp
  // their work.
  useEffect(() => {
    if (data && !dirty) setContent(data.current ?? '')
  }, [data, dirty])

  function onChange(v) {
    setContent(v)
    setDirty(true)
    setActionError(null)
    setSavedNote(null)
    setConfirmingReset(false)
  }

  async function handleSave() {
    setBusy(true)
    setActionError(null)
    setSavedNote(null)
    try {
      await save(content)
      setDirty(false)
      setSavedNote('Saved')
    } catch (e) {
      setActionError(e.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleReset() {
    setBusy(true)
    setActionError(null)
    setSavedNote(null)
    try {
      const d = await reset()
      setContent(d.current ?? '')
      setDirty(false)
      setSavedNote('Reset to built-in')
    } catch (e) {
      setActionError(e.message || 'Reset failed')
    } finally {
      setBusy(false)
      setConfirmingReset(false)
    }
  }

  function handleDiscard() {
    setContent(data?.current ?? '')
    setDirty(false)
    setActionError(null)
    setSavedNote(null)
    setConfirmingReset(false)
  }

  const isEmpty = !content.trim()
  const customized = !!data?.customized

  return (
    <div className="border border-border rounded bg-app">
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border">
        <div className="text-sm text-fg-muted">
          <i className="fa-solid fa-message mr-2 text-fg-subtle"></i>
          Default system prompt
          {customized && (
            <span className="ml-2 text-xs text-warning-fg border border-warning rounded px-1.5 py-0.5">
              Modified from built-in
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {savedNote && <span className="text-xs text-success-fg">{savedNote}</span>}
          {dirty && <span className="text-xs text-warning-fg">Unsaved</span>}

          {confirmingReset ? (
            <>
              <span className="text-xs text-fg-muted">Reset to built-in?</span>
              <button
                onClick={handleReset}
                disabled={busy}
                className="text-xs px-2 py-1 rounded bg-danger hover:bg-danger text-white disabled:opacity-50"
              >
                Confirm reset
              </button>
              <button
                onClick={() => setConfirmingReset(false)}
                disabled={busy}
                className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleDiscard}
                disabled={busy || !dirty}
                className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
              >
                Discard
              </button>
              <button
                onClick={() => { setConfirmingReset(true); setActionError(null); setSavedNote(null) }}
                disabled={busy || !customized}
                title={customized ? 'Discard the customization and revert to the built-in prompt' : 'Already using the built-in prompt'}
                className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
              >
                Reset to built-in
              </button>
              <button
                onClick={handleSave}
                disabled={busy || !dirty || isEmpty}
                className="text-xs px-2 py-1 rounded bg-accent-strong hover:bg-accent-hover disabled:opacity-50 text-white"
              >
                Save
              </button>
            </>
          )}
        </div>
      </div>

      <p className="px-3 pt-2 text-xs text-fg-subtle">
        Applied to every new conversation. Existing conversations keep their own copy and are unaffected.
        Tool-specific guidance belongs in each MCP server's <span className="font-mono">tool_hint</span>, not here.
      </p>

      {loading ? (
        <div className="px-3 py-6 text-sm text-fg-subtle">
          <i className="fa-solid fa-spinner fa-spin mr-2"></i>Loading…
        </div>
      ) : (
        <textarea
          value={content}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          disabled={busy}
          className="w-full h-64 bg-surface-muted text-fg font-mono text-xs p-3 mt-2 focus:outline-none resize-y disabled:opacity-60"
          placeholder="The default system prompt for new conversations…"
        />
      )}

      {(error || actionError || isEmpty) && !loading && (
        <div className="px-3 py-2 border-t border-border text-xs space-y-1">
          {error && (
            <div className="text-danger-fg"><i className="fa-solid fa-triangle-exclamation mr-1"></i>{error}</div>
          )}
          {actionError && (
            <div className="text-danger-fg"><i className="fa-solid fa-triangle-exclamation mr-1"></i>{actionError}</div>
          )}
          {isEmpty && (
            <div className="text-warning-fg"><i className="fa-solid fa-triangle-exclamation mr-1"></i>Prompt cannot be empty.</div>
          )}
        </div>
      )}
    </div>
  )
}
