import { useEffect, useState } from 'react'

const EXAMPLE = `{
  "websearch": {
    "enabled": true,
    "name": "Web Search",
    "description": "Search the web via the configured websearch MCP provider",
    "command": "/abs/path/to/websearch-mcp/.venv/bin/python",
    "args": ["/abs/path/to/websearch-mcp/main.py", "--transport", "stdio"],
    "icon": "fa-magnifying-glass",
    "tool_hint": "Use web_search for current/external information."
  }
}`

export default function RegistryEditor({ initialContent, configPath, externalErrors, loadError, onSave, onReload }) {
  const [content, setContent] = useState(initialContent || '')
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [saveEntryErrors, setSaveEntryErrors] = useState([])
  const [savedNote, setSavedNote] = useState(null)

  useEffect(() => {
    if (!dirty) setContent(initialContent || '')
  }, [initialContent, dirty])

  function onChange(v) {
    setContent(v)
    setDirty(true)
    setSaveError(null)
    setSaveEntryErrors([])
    setSavedNote(null)
  }

  async function handleSave() {
    setBusy(true)
    setSaveError(null)
    setSaveEntryErrors([])
    setSavedNote(null)
    try {
      await onSave(content)
      setDirty(false)
      setSavedNote('Saved')
    } catch (e) {
      setSaveError(e.message || 'Save failed')
      setSaveEntryErrors(e.body?.entry_errors || [])
    } finally {
      setBusy(false)
    }
  }

  async function handleReload() {
    setBusy(true)
    setSaveError(null)
    setSaveEntryErrors([])
    setSavedNote(null)
    try {
      await onReload()
      setDirty(false)
    } catch (e) {
      setSaveError(e.message || 'Reload failed')
    } finally {
      setBusy(false)
    }
  }

  function handleDiscard() {
    setContent(initialContent || '')
    setDirty(false)
    setSaveError(null)
    setSaveEntryErrors([])
    setSavedNote(null)
  }

  function handleInsertExample() {
    setContent(content.trim() ? content : EXAMPLE)
    setDirty(true)
  }

  return (
    <div className="border border-border rounded bg-app">
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border">
        <div className="text-sm text-fg-muted">
          <i className="fa-solid fa-file-code mr-2 text-fg-subtle"></i>
          External registry JSON
          {configPath && (
            <span className="ml-2 text-xs text-fg-subtle font-mono">{configPath}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {savedNote && <span className="text-xs text-success-fg">{savedNote}</span>}
          {dirty && <span className="text-xs text-warning-fg">Unsaved</span>}
          <button
            onClick={handleInsertExample}
            disabled={busy}
            className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
          >
            Insert example
          </button>
          <button
            onClick={handleDiscard}
            disabled={busy || !dirty}
            className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
          >
            Discard
          </button>
          <button
            onClick={handleReload}
            disabled={busy}
            className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong disabled:opacity-50"
          >
            Reload from disk
          </button>
          <button
            onClick={handleSave}
            disabled={busy || !dirty}
            className="text-xs px-2 py-1 rounded bg-accent-strong hover:bg-accent-hover disabled:opacity-50 text-white"
          >
            Save
          </button>
        </div>
      </div>

      <textarea
        value={content}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        className="w-full h-72 bg-surface-muted text-fg font-mono text-xs p-3 focus:outline-none resize-y"
        placeholder='{ "my-tool": { "enabled": true, "name": "...", "command": "/abs/path", "args": [], ... } }'
      />

      {(loadError || saveError || (externalErrors && externalErrors.length > 0) || saveEntryErrors.length > 0) && (
        <div className="px-3 py-2 border-t border-border text-xs space-y-1">
          {loadError && (
            <div className="text-danger-fg"><i className="fa-solid fa-triangle-exclamation mr-1"></i>Load: {loadError}</div>
          )}
          {saveError && (
            <div className="text-danger-fg"><i className="fa-solid fa-triangle-exclamation mr-1"></i>{saveError}</div>
          )}
          {saveEntryErrors.map((err, i) => (
            <div key={`save-${i}`} className="text-danger-fg">
              <span className="font-mono text-fg-subtle">{err.entry_id || '(top-level)'}:</span> {err.message}
            </div>
          ))}
          {externalErrors && externalErrors.map((err, i) => (
            <div key={`ext-${i}`} className="text-warning-fg">
              <span className="font-mono text-fg-subtle">{err.entry_id || '(top-level)'}:</span> {err.message}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
