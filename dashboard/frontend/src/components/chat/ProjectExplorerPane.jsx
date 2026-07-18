import { useState, useEffect, useCallback, useRef } from 'react'
import { getProjectFilesTree, uploadProjectFile } from '../../services/chat'
import { findNode } from './projectTreeUtils'
import { TreeFile, TreeDir } from './projectTree'

// File-explorer strip shown to the left of the chat when the conversation
// belongs to a project. Read-mostly: browse the tree, open a file in the
// editor overlay, create a file, upload into the root, refresh. The full
// explorer (move/copy/delete/DnD) stays on the project page.
export default function ProjectExplorerPane({ project, refreshKey = 0, editingPath = null, onOpenFile, onCollapse }) {
  const [tree, setTree] = useState([])
  const [expanded, setExpanded] = useState(() => new Set())
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const fileInputRef = useRef(null)
  // Monotonic request generation + project binding, same discipline as
  // ProjectPage: a slow response for the previous project must not
  // install its rows under the project now displayed.
  const genRef = useRef(0)
  const projectIdRef = useRef(project?.id)
  projectIdRef.current = project?.id

  const refresh = useCallback(async () => {
    const pid = project?.id
    if (!pid) return
    if (projectIdRef.current !== pid) return
    const gen = ++genRef.current
    const stillCurrent = () => genRef.current === gen && projectIdRef.current === pid
    try {
      const data = await getProjectFilesTree(pid)
      if (!stillCurrent()) return
      setTree(data.tree || [])
      setError(null)
    } catch (err) {
      if (!stillCurrent()) return
      setError(err.message)
    }
  }, [project?.id])

  useEffect(() => {
    setTree([])
    setExpanded(new Set())
    setError(null)
    setBusy(false)
    refresh()
  }, [refresh])

  // External refresh signal (a chat run finished and may have written
  // files, the editor overlay saved, …). Only key CHANGES refresh — the
  // mount-time value is already covered by the effect above, and the key
  // stays positive after the first completed run, so re-firing on mount
  // would double-fetch every time the pane (re)appears.
  const lastKeyRef = useRef(refreshKey)
  useEffect(() => {
    if (refreshKey !== lastKeyRef.current) {
      lastKeyRef.current = refreshKey
      refresh()
    }
  }, [refreshKey, refresh])

  const toggle = useCallback((path) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }, [])

  const handleNewFile = useCallback(() => {
    const name = window.prompt('File name')
    if (!name || !name.trim()) return
    const path = name.trim().replace(/^\/+|\/+$/g, '')
    if (!path) return
    // If it already exists, open it instead of silently overwriting on save.
    const existing = findNode(tree, path)
    onOpenFile?.(path, !existing)
  }, [tree, onOpenFile])

  const handleFilesPicked = useCallback(async (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = '' // allow re-picking the same file later
    if (files.length === 0) return
    const pid = project?.id
    setBusy(true)
    setError(null)
    try {
      for (const file of files) {
        try {
          await uploadProjectFile(pid, file, { dir: '' })
        } catch (err) {
          if (err.code === 'already_exists' &&
              window.confirm(`"${file.name}" already exists. Overwrite?`)) {
            await uploadProjectFile(pid, file, { dir: '', overwrite: true })
          } else if (err.code !== 'already_exists') {
            throw err
          }
        }
      }
      await refresh()
    } catch (err) {
      if (projectIdRef.current === pid) setError(err.message)
    } finally {
      if (projectIdRef.current === pid) setBusy(false)
    }
  }, [project?.id, refresh])

  if (!project) return null

  return (
    <div className="h-full flex flex-col bg-app select-none" data-testid="project-explorer-pane">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        onChange={handleFilesPicked}
        className="hidden"
        data-testid="explorer-file-input"
      />

      {/* Header: project name + collapse */}
      <div className="px-3 py-2 border-b border-border flex items-center gap-2 flex-shrink-0">
        <i className="fa-solid fa-folder-open text-xs text-amber-500/80 flex-shrink-0"></i>
        <span className="flex-1 min-w-0 truncate text-xs font-semibold text-fg uppercase tracking-wide">
          {project.name}
        </span>
        <button
          onClick={onCollapse}
          className="text-fg-subtle hover:text-fg p-1 -m-1 cursor-pointer"
          title="Hide file explorer"
          aria-label="Hide file explorer"
        >
          <i className="fa-solid fa-angles-left text-sm"></i>
        </button>
      </div>

      {error && (
        <div className="mx-2 mt-2 px-2 py-1.5 bg-danger-subtle text-danger-fg rounded text-xs">
          {error}
        </div>
      )}

      {/* Tree */}
      <div className="flex-1 overflow-auto py-2 px-1.5">
        {tree.length === 0 && !error && (
          <div className="p-4 text-center text-[11px] text-fg-subtle">
            No files yet.
          </div>
        )}
        {tree.map(node => (
          node.type === 'dir' ? (
            <TreeDir
              key={node.path}
              node={node}
              depth={0}
              expanded={expanded}
              editingPath={editingPath}
              onToggle={toggle}
              onOpenFile={(n) => onOpenFile?.(n.path, false)}
            />
          ) : (
            <TreeFile
              key={node.path}
              node={node}
              depth={0}
              editingPath={editingPath}
              onOpen={(n) => onOpenFile?.(n.path, false)}
            />
          )
        ))}
      </div>

      {/* Footer actions */}
      <div className="px-2 py-1.5 border-t border-border flex items-center justify-around flex-shrink-0">
        <button
          onClick={handleNewFile}
          disabled={busy}
          className="text-fg-subtle hover:text-fg p-1.5 cursor-pointer disabled:opacity-50"
          title="New file" aria-label="New file"
        >
          <i className="fa-solid fa-file-circle-plus text-xs"></i>
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={busy}
          className="text-fg-subtle hover:text-fg p-1.5 cursor-pointer disabled:opacity-50"
          title="Upload files" aria-label="Upload files"
        >
          <i className="fa-solid fa-file-arrow-up text-xs"></i>
        </button>
        <button
          onClick={refresh}
          disabled={busy}
          className="text-fg-subtle hover:text-fg p-1.5 cursor-pointer disabled:opacity-50"
          title="Refresh" aria-label="Refresh file tree"
        >
          <i className="fa-solid fa-rotate-right text-xs"></i>
        </button>
      </div>
    </div>
  )
}
