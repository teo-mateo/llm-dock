import { useState, useCallback, useMemo } from 'react'
import useChatPrompts from '../hooks/useChatPrompts'

const PREVIEW_LEN = 150

function truncatePreview(content, maxLen = PREVIEW_LEN) {
  if (!content) return ''
  const trimmed = content.trim()
  if (trimmed.length <= maxLen) return trimmed
  return trimmed.slice(0, maxLen) + '…'
}

function PromptForm({ initialName, initialContent, onSave, onCancel, saving, error }) {
  const [name, setName] = useState(initialName)
  const [content, setContent] = useState(initialContent)

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault()
    if (!name.trim() || !content.trim()) return
    try {
      await onSave(name.trim(), content)
    } catch (e) {
      console.error(e)
    }
  }, [name, content, onSave])

  const nameValid = name.trim().length > 0
  const contentValid = content.trim().length > 0

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && (
        <div className="text-xs text-danger-fg bg-danger-subtle border border-danger rounded px-3 py-2">
          {error}
        </div>
      )}
      {!nameValid && (
        <p className="text-xs text-warning-fg">
          <i className="fa-solid fa-triangle-exclamation mr-1"></i>Name is required.
        </p>
      )}
      {!contentValid && (
        <p className="text-xs text-warning-fg">
          <i className="fa-solid fa-triangle-exclamation mr-1"></i>Content is required.
        </p>
      )}
      <input
        type="text"
        value={name}
        onChange={e => setName(e.target.value)}
        placeholder="Prompt name"
        className="w-full bg-surface border border-border rounded px-3 py-2 text-xs text-fg focus:outline-none focus:border-accent-strong"
      />
      <textarea
        value={content}
        onChange={e => setContent(e.target.value)}
        placeholder="Prompt content"
        className="w-full h-64 bg-surface-muted text-fg font-mono text-xs p-3 rounded border border-border focus:outline-none focus:border-accent-strong resize-none"
      />
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving || !nameValid || !contentValid}
          className="text-xs px-2 py-1 rounded bg-accent-strong text-white hover:bg-accent-hover disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong text-fg"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

function PromptRow({ prompt, index, total, onEdit, onDelete, onMoveUp, onMoveDown }) {
  const [expanded, setExpanded] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  const preview = truncatePreview(prompt.content)
  const isLong = prompt.content && prompt.content.trim().length > PREVIEW_LEN

  const handleDelete = useCallback(() => {
    setShowConfirm(true)
  }, [])

  const confirmDelete = useCallback(() => {
    onDelete(prompt.id)
    setShowConfirm(false)
  }, [prompt.id, onDelete])

  const cancelDelete = useCallback(() => {
    setShowConfirm(false)
  }, [])

  return (
    <div className="border border-border rounded-lg p-4 space-y-3">
      {showConfirm && (
        <div className="flex items-center gap-2 text-xs">
          <span>Delete "{prompt.name}"?</span>
          <button
            onClick={confirmDelete}
            className="text-xs px-2 py-1 rounded bg-danger hover:bg-danger/80 text-white"
          >
            Yes
          </button>
          <button
            onClick={cancelDelete}
            className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong text-fg"
          >
            No
          </button>
        </div>
      )}

      {!showConfirm && (
        <>
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-fg">{prompt.name}</div>
              <div
                className="text-xs text-fg-subtle mt-1 whitespace-pre-wrap break-words"
                title={prompt.content}
              >
                {expanded ? prompt.content : preview}
                {isLong && (
                  <button
                    onClick={() => setExpanded(!expanded)}
                    className="ml-1 text-xs text-accent-fg hover:text-accent-fg-hover underline"
                  >
                    {expanded ? 'Less' : 'More'}
                  </button>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={() => onMoveUp(index)}
                disabled={index === 0}
                title="Move up"
                className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong text-fg-muted disabled:opacity-30"
              >
                <i className="fa-solid fa-up-long"></i>
              </button>
              <button
                onClick={() => onMoveDown(index, total)}
                disabled={index === total - 1}
                title="Move down"
                className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong text-fg-muted disabled:opacity-30"
              >
                <i className="fa-solid fa-down-long"></i>
              </button>
              <button
                onClick={() => onEdit(prompt)}
                title="Edit"
                className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong text-fg-muted"
              >
                <i className="fa-solid fa-pen"></i>
              </button>
              <button
                onClick={handleDelete}
                title="Delete"
                className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong text-danger-fg"
              >
                <i className="fa-solid fa-trash"></i>
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default function PromptsEditor() {
  const { prompts, loading, error, create, update, remove, reorder } = useChatPrompts()

  const [editingPrompt, setEditingPrompt] = useState(null)
  const [adding, setAdding] = useState(false)
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState(null)

  const sorted = useMemo(() => {
    return [...(prompts || [])].sort(
      (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0),
    )
  }, [prompts])

  const setFeedbackWithClear = useCallback((msg, isError = false) => {
    setFeedback({ message: msg, isError })
    const t = setTimeout(() => setFeedback(null), 3000)
    return () => clearTimeout(t)
  }, [])

  const handleAdd = useCallback(async (name, content) => {
    setSaving(true)
    try {
      await create(name, content)
      setAdding(false)
      setFeedbackWithClear('Prompt created.', false)
    } catch (e) {
      setFeedbackWithClear(e.message || 'Failed to create prompt.', true)
    } finally {
      setSaving(false)
    }
  }, [create, setFeedbackWithClear])

  const handleEdit = useCallback(async (name, content) => {
    setSaving(true)
    try {
      await update(editingPrompt.id, name, content)
      setEditingPrompt(null)
      setFeedbackWithClear('Prompt saved.', false)
    } catch (e) {
      setFeedbackWithClear(e.message || 'Failed to save prompt.', true)
    } finally {
      setSaving(false)
    }
  }, [update, editingPrompt, setFeedbackWithClear])

  const handleDelete = useCallback(async (id) => {
    try {
      await remove(id)
      setFeedbackWithClear('Prompt deleted.', false)
    } catch (e) {
      setFeedbackWithClear(e.message || 'Failed to delete prompt.', true)
    }
  }, [remove, setFeedbackWithClear])

  const handleMoveUp = useCallback(async (index) => {
    if (index === 0) return
    const newIds = sorted.map(p => p.id)
    const tmp = newIds[index]
    newIds[index] = newIds[index - 1]
    newIds[index - 1] = tmp
    try {
      await reorder(newIds)
    } catch (e) {
      setFeedbackWithClear(e.message || 'Failed to reorder prompts.', true)
    }
  }, [sorted, reorder, setFeedbackWithClear])

  const handleMoveDown = useCallback(async (index) => {
    if (index === sorted.length - 1) return
    const newIds = sorted.map(p => p.id)
    const tmp = newIds[index]
    newIds[index] = newIds[index + 1]
    newIds[index + 1] = tmp
    try {
      await reorder(newIds)
    } catch (e) {
      setFeedbackWithClear(e.message || 'Failed to reorder prompts.', true)
    }
  }, [sorted, reorder, setFeedbackWithClear])

  const handleCancelAdd = useCallback(() => {
    setAdding(false)
  }, [])

  const handleCancelEdit = useCallback(() => {
    setEditingPrompt(null)
  }, [])

  const handleEditClick = useCallback((prompt) => {
    setEditingPrompt(prompt)
  }, [])

  return (
    <div className="bg-surface border border-border rounded-lg p-6">
      <h2 className="text-lg font-medium text-fg mb-4">Managed System Prompts</h2>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-fg-muted">
          <i className="fa-solid fa-spinner fa-spin"></i>
          Loading prompts...
        </div>
      )}

      {error && !loading && (
        <div className="text-xs text-danger-fg bg-danger-subtle border border-danger rounded px-3 py-2">
          {error}
        </div>
      )}

      {!loading && !error && (
        <>
          {feedback && (
            <div className={`mb-4 text-xs ${feedback.isError ? 'text-danger-fg' : 'text-success-fg'}`}>
              <i className={`fa-solid fa-${feedback.isError ? 'circle-xmark' : 'circle-check'} mr-1`}></i>
              {feedback.message}
            </div>
          )}

          {!adding && !editingPrompt && (
            <button
              onClick={() => setAdding(true)}
              className="text-xs px-2 py-1 rounded bg-accent-strong text-white hover:bg-accent-hover mb-4"
            >
              <i className="fa-solid fa-plus mr-1"></i>Add Prompt
            </button>
          )}

          {adding && (
            <div className="mb-4">
              <PromptForm
                initialName=""
                initialContent=""
                onSave={handleAdd}
                onCancel={handleCancelAdd}
                saving={saving}
                error={null}
              />
            </div>
          )}

          {editingPrompt && (
            <div className="mb-4">
              <PromptForm
                initialName={editingPrompt.name}
                initialContent={editingPrompt.content}
                onSave={handleEdit}
                onCancel={handleCancelEdit}
                saving={saving}
                error={null}
              />
            </div>
          )}

          {!adding && !editingPrompt && sorted.length === 0 && (
            <p className="text-xs text-fg-muted">No managed prompts yet. Add one to get started.</p>
          )}

          {!adding && !editingPrompt && sorted.length > 0 && (
            <div className="space-y-2">
              {sorted.map((prompt, index) => (
                <PromptRow
                  key={prompt.id}
                  prompt={prompt}
                  index={index}
                  total={sorted.length}
                  onEdit={handleEditClick}
                  onDelete={handleDelete}
                  onMoveUp={handleMoveUp}
                  onMoveDown={handleMoveDown}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
