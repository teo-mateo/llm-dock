import { useEffect, useState } from 'react'
import useOpenRouterModels from '../../hooks/useOpenRouterModels'

const toJson = (models) => JSON.stringify(models ?? [], null, 2)

// Client-side mirror of the server validation, so Save can be gated and the
// error shown before a round-trip. Returns an error string or null.
function validateModelsJson(text) {
  let parsed
  try {
    parsed = JSON.parse(text)
  } catch (e) {
    return `Invalid JSON: ${e.message}`
  }
  if (!Array.isArray(parsed)) return 'Top level must be an array of {id, label?} objects.'
  const seen = new Set()
  for (const entry of parsed) {
    if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) {
      return 'Each model must be an object with an "id".'
    }
    if (typeof entry.id !== 'string' || !entry.id.trim()) {
      return 'Each model must have a non-empty string "id".'
    }
    if (entry.label !== undefined && typeof entry.label !== 'string') {
      return '"label" must be a string when present.'
    }
    if (seen.has(entry.id.trim())) return `Duplicate model id: ${entry.id.trim()}`
    seen.add(entry.id.trim())
  }
  return null
}

// Editor for the curated OpenRouter model list shown in the chat model
// pickers. The list is a picker convenience, not an allowlist — existing
// conversations keep working if their model is removed here.
export default function OpenRouterModelsEditor() {
  const { data, loading, error, save, reset } = useOpenRouterModels()

  const [content, setContent] = useState('[]')
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState(null)
  const [savedNote, setSavedNote] = useState(null)
  const [confirmingReset, setConfirmingReset] = useState(false)

  // Sync the textarea from the server value whenever it changes — but not
  // while the user has unsaved edits, so a background refresh can't stomp
  // their work.
  useEffect(() => {
    if (data && !dirty) setContent(toJson(data.current))
  }, [data, dirty])

  function onChange(v) {
    setContent(v)
    setDirty(true)
    setActionError(null)
    setSavedNote(null)
    setConfirmingReset(false)
  }

  const validationError = dirty ? validateModelsJson(content) : null

  async function handleSave() {
    setBusy(true)
    setActionError(null)
    setSavedNote(null)
    try {
      const d = await save(JSON.parse(content))
      setContent(toJson(d.current))
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
      setContent(toJson(d.current))
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
    setContent(toJson(data?.current))
    setDirty(false)
    setActionError(null)
    setSavedNote(null)
    setConfirmingReset(false)
  }

  const customized = !!data?.customized
  const configured = !!data?.configured

  return (
    <div className="border border-border rounded bg-app">
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border">
        <div className="text-sm text-fg-muted">
          <i className="fa-solid fa-cloud mr-2 text-fg-subtle"></i>
          OpenRouter models
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
                title={customized ? 'Discard the customization and revert to the built-in list' : 'Already using the built-in list'}
                className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
              >
                Reset to built-in
              </button>
              <button
                onClick={handleSave}
                disabled={busy || !dirty || !!validationError}
                className="text-xs px-2 py-1 rounded bg-accent-strong hover:bg-accent-hover disabled:opacity-50 text-white"
              >
                Save
              </button>
            </>
          )}
        </div>
      </div>

      <p className="px-3 pt-2 text-xs text-fg-subtle">
        Curated models offered in the chat model pickers, as{' '}
        <span className="font-mono">{'[{"id": "vendor/model", "label": "…"}]'}</span>.
        Removing a model here does not break conversations already using it.
      </p>

      {!configured && !loading && (
        <div className="mx-3 mt-2 text-xs text-warning-fg bg-app border border-warning rounded px-3 py-2">
          <i className="fa-solid fa-triangle-exclamation mr-1"></i>
          <span className="font-mono">OPENROUTER_API_KEY</span> is not set in{' '}
          <span className="font-mono">dashboard/.env</span> — these models won't appear in the chat picker until it is.
        </div>
      )}

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
          placeholder='[{"id": "anthropic/claude-sonnet-5", "label": "Claude Sonnet 5"}]'
        />
      )}

      {(error || actionError || validationError) && !loading && (
        <div className="px-3 py-2 border-t border-border text-xs space-y-1">
          {error && (
            <div className="text-danger-fg"><i className="fa-solid fa-triangle-exclamation mr-1"></i>{error}</div>
          )}
          {actionError && (
            <div className="text-danger-fg"><i className="fa-solid fa-triangle-exclamation mr-1"></i>{actionError}</div>
          )}
          {validationError && (
            <div className="text-warning-fg"><i className="fa-solid fa-triangle-exclamation mr-1"></i>{validationError}</div>
          )}
        </div>
      )}
    </div>
  )
}
