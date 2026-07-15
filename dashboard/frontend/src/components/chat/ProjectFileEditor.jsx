import { useState, useEffect, useCallback, useRef } from 'react'
import { getProjectFileContent, saveProjectFileContent } from '../../services/chat'

// Lightweight text editor for a single project file: plain textarea,
// dirty tracking, Ctrl/Cmd+S, and optimistic-concurrency saves (the
// loaded mtime is sent as base_modified_at; a 409 means the file changed
// on disk and the user chooses to reload or overwrite).
export default function ProjectFileEditor({ projectId, path, isNew = false, onClose, onSaved }) {
  const [content, setContent] = useState('')
  const [baseModifiedAt, setBaseModifiedAt] = useState(null)
  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(isNew)
  const [error, setError] = useState(null)
  const [conflict, setConflict] = useState(false)
  const textareaRef = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setConflict(false)
    try {
      const doc = await getProjectFileContent(projectId, path)
      setContent(doc.content)
      setBaseModifiedAt(doc.modified_at)
      setDirty(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [projectId, path])

  useEffect(() => {
    if (!isNew) load()
  }, [load, isNew])

  const save = useCallback(async ({ force = false } = {}) => {
    setSaving(true)
    setError(null)
    setConflict(false)
    try {
      const node = await saveProjectFileContent(
        projectId, path, content,
        force ? null : baseModifiedAt,
      )
      setBaseModifiedAt(node.modified_at)
      setDirty(false)
      onSaved?.()
    } catch (err) {
      if (err.message.includes('changed on disk')) {
        setConflict(true)
      } else {
        setError(err.message)
      }
    } finally {
      setSaving(false)
    }
  }, [projectId, path, content, baseModifiedAt, onSaved])

  const handleKeyDown = useCallback((e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault()
      if (dirty && !saving) save()
    }
  }, [dirty, saving, save])

  const handleClose = useCallback(() => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    onClose()
  }, [dirty, onClose])

  return (
    <div className="flex-1 flex flex-col overflow-hidden" data-testid="file-editor">
      {/* Editor header */}
      <div className="px-6 py-2 border-b border-border flex items-center gap-3">
        <i className="fa-regular fa-file-lines text-fg-faint text-xs"></i>
        <span className="text-sm text-fg font-medium truncate">{path}</span>
        {dirty && (
          <span className="text-[10px] px-1.5 py-0.5 bg-warning-subtle text-warning-fg rounded"
                title="Unsaved changes" data-testid="dirty-indicator">modified</span>
        )}
        <span className="ml-auto flex items-center gap-2">
          <button
            onClick={() => save()}
            disabled={!dirty || saving || loading}
            className="px-3 py-1.5 bg-accent-strong hover:bg-accent-hover text-fg-inverse rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            onClick={handleClose}
            className="px-2 py-1.5 text-fg-subtle hover:text-fg text-xs"
            title="Close editor" aria-label="Close editor"
          >
            <i className="fa-solid fa-xmark"></i>
          </button>
        </span>
      </div>

      {conflict && (
        <div className="mx-6 mt-3 px-3 py-2 bg-warning-subtle text-warning-fg rounded text-xs flex items-center gap-3">
          <span>The file changed on disk since it was loaded.</span>
          <button onClick={load} className="underline">Reload (discard my changes)</button>
          <button onClick={() => save({ force: true })} className="underline">Overwrite anyway</button>
        </div>
      )}
      {error && (
        <div className="mx-6 mt-3 px-3 py-2 bg-danger-subtle text-danger-fg rounded text-xs">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-fg-subtle text-sm">
          Loading…
        </div>
      ) : (
        <textarea
          ref={textareaRef}
          value={content}
          onChange={e => { setContent(e.target.value); setDirty(true) }}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          className="flex-1 w-full resize-none bg-app text-fg font-mono text-sm leading-relaxed p-6 focus:outline-none"
          placeholder={isNew ? 'New file — start typing…' : ''}
          data-testid="editor-textarea"
        />
      )}
    </div>
  )
}
