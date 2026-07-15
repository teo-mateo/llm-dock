import { useState, useEffect, useCallback, useRef } from 'react'
import { getProjectFileContent, saveProjectFileContent } from '../../services/chat'

// Lightweight text editor for a single project file: plain textarea,
// dirty tracking, Ctrl/Cmd+S, and optimistic-concurrency saves (the
// loaded revision is sent as base_revision; a 409 means the file changed
// on disk and the user chooses to reload or overwrite).
export default function ProjectFileEditor({ projectId, path, isNew = false, onClose, onSaved, onDirtyChange }) {
  const [content, setContent] = useState('')
  const [baseRevision, setBaseRevision] = useState(null)
  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(isNew)
  const [error, setError] = useState(null)
  const [conflict, setConflict] = useState(null) // conflict message | null
  const textareaRef = useRef(null)
  // Latest textarea content, for comparing against the snapshot a save
  // actually submitted — the user may keep typing while a save is in
  // flight, and that newer content must stay marked dirty.
  const contentRef = useRef('')
  // Whether the next save should carry the create-only precondition.
  // Starts from isNew, and drops permanently once the file demonstrably
  // exists — after any successful save OR after loading it from disk
  // (the reload path of an already-exists conflict).
  const createModeRef = useRef(isNew)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setConflict(null)
    try {
      const doc = await getProjectFileContent(projectId, path)
      setContent(doc.content)
      contentRef.current = doc.content
      createModeRef.current = false
      setBaseRevision(doc.revision)
      setDirty(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [projectId, path])

  // Initial load decision is taken from createModeRef, NOT the isNew prop:
  // after the first successful save the parent flips isNew to false, and a
  // prop-driven load() would refetch the just-saved snapshot and clobber
  // anything typed while that save was in flight. The effect re-runs only
  // when projectId/path change — which remounts the editor anyway (keyed
  // by path in ProjectPage).
  useEffect(() => {
    if (!createModeRef.current) load()
  }, [load])

  const save = useCallback(async ({ force = false } = {}) => {
    // `content` is the snapshot this save submits. The user can keep
    // typing while the request is in flight — only clear dirty if the
    // textarea still holds exactly what was saved.
    const submitted = content
    setSaving(true)
    setError(null)
    setConflict(null)
    try {
      const node = await saveProjectFileContent(
        projectId, path, submitted,
        force ? null : baseRevision,
        // New-file precondition: the tree snapshot said this path is free,
        // but the filesystem is the source of truth — create-only turns a
        // stale snapshot into a 409 instead of a silent overwrite. A
        // forced save is the explicit overwrite escape hatch.
        createModeRef.current && !force,
      )
      createModeRef.current = false
      setBaseRevision(node.revision)
      setDirty(contentRef.current !== submitted)
      onSaved?.()
    } catch (err) {
      if (err.message.includes('changed on disk') || err.message.includes('already exists')) {
        setConflict(err.message.includes('already exists')
          ? 'A file with this name already exists on disk.'
          : 'The file changed on disk since it was loaded.')
      } else {
        setError(err.message)
      }
    } finally {
      setSaving(false)
    }
  }, [projectId, path, content, baseRevision, onSaved])

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

  // Surface dirty state to the parent so in-app navigation (sidebar
  // clicks route away and unmount this editor without handleClose) can
  // guard against silent discards. Reset on unmount.
  const onDirtyChangeRef = useRef(onDirtyChange)
  onDirtyChangeRef.current = onDirtyChange
  useEffect(() => {
    onDirtyChangeRef.current?.(dirty)
  }, [dirty])
  useEffect(() => () => onDirtyChangeRef.current?.(false), [])

  // Browser close/reload guard while dirty.
  useEffect(() => {
    if (!dirty) return
    const handler = (e) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

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
          <span>{conflict}</span>
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
          onChange={e => { setContent(e.target.value); contentRef.current = e.target.value; setDirty(true) }}
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
