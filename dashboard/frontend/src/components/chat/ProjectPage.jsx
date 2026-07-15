import { useState, useEffect, useCallback, useRef } from 'react'
import {
  getProjectFilesTree, uploadProjectFile, mkdirProjectPath,
  moveProjectPath, deleteProjectPath, downloadProjectFile,
} from '../../services/chat'

function formatSize(bytes) {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function NodeRow({ node, depth, expanded, onToggle, onUploadInto, onNewFolder, onRename, onDelete, onDownload }) {
  const isDir = node.type === 'dir'
  return (
    <>
      <div
        onClick={isDir ? () => onToggle(node.path) : undefined}
        className={`group flex items-center gap-2 py-1.5 pr-3 border-b border-border-subtle text-sm ${
          isDir ? 'cursor-pointer text-fg' : 'text-fg-muted'
        } hover:bg-surface-muted`}
        style={{ paddingLeft: `${12 + depth * 18}px` }}
        data-testid={`file-row-${node.path}`}
      >
        {isDir ? (
          <>
            <i className={`fa-solid fa-chevron-${expanded.has(node.path) ? 'down' : 'right'} text-[9px] w-3 text-fg-faint flex-shrink-0`}></i>
            <i className="fa-solid fa-folder text-xs text-amber-500/80 flex-shrink-0"></i>
          </>
        ) : (
          <>
            <span className="w-3 flex-shrink-0"></span>
            <i className="fa-regular fa-file text-xs text-fg-faint flex-shrink-0"></i>
          </>
        )}
        <span className="flex-1 min-w-0 truncate">{node.name}</span>
        {!isDir && <span className="text-[10px] text-fg-faint flex-shrink-0">{formatSize(node.size)}</span>}
        <span className="flex items-center gap-0.5 flex-shrink-0">
          {isDir && (
            <>
              <button
                onClick={e => { e.stopPropagation(); onUploadInto(node.path) }}
                className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-fg p-1 cursor-pointer"
                title="Upload into folder" aria-label={`Upload into ${node.path}`}
              ><i className="fa-solid fa-file-arrow-up text-xs"></i></button>
              <button
                onClick={e => { e.stopPropagation(); onNewFolder(node.path) }}
                className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-fg p-1 cursor-pointer"
                title="New subfolder" aria-label={`New subfolder in ${node.path}`}
              ><i className="fa-solid fa-folder-plus text-xs"></i></button>
            </>
          )}
          {!isDir && (
            <button
              onClick={e => { e.stopPropagation(); onDownload(node) }}
              className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-fg p-1 cursor-pointer"
              title="Download" aria-label={`Download ${node.path}`}
            ><i className="fa-solid fa-download text-xs"></i></button>
          )}
          <button
            onClick={e => { e.stopPropagation(); onRename(node) }}
            className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-fg p-1 cursor-pointer"
            title="Rename / move" aria-label={`Rename ${node.path}`}
          ><i className="fa-solid fa-pen text-xs"></i></button>
          <button
            onClick={e => { e.stopPropagation(); onDelete(node) }}
            className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-danger-fg p-1 cursor-pointer"
            title="Delete" aria-label={`Delete ${node.path}`}
          ><i className="fa-solid fa-trash text-xs"></i></button>
        </span>
      </div>
      {isDir && expanded.has(node.path) && (node.children || []).map(child => (
        <NodeRow
          key={child.path}
          node={child}
          depth={depth + 1}
          expanded={expanded}
          onToggle={onToggle}
          onUploadInto={onUploadInto}
          onNewFolder={onNewFolder}
          onRename={onRename}
          onDelete={onDelete}
          onDownload={onDownload}
        />
      ))}
    </>
  )
}

export default function ProjectPage({ project }) {
  const [tree, setTree] = useState([])
  const [expanded, setExpanded] = useState(() => new Set())
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const fileInputRef = useRef(null)
  // Directory the next file-picker selection uploads into.
  const uploadDirRef = useRef('')
  // Monotonic request generation. A tree fetch only commits if it is still
  // the latest — otherwise a slow response for project A, resolving after
  // the user switched to project B, would install A's rows under B and
  // route row actions (which close over B's id) at the wrong project.
  const genRef = useRef(0)
  // The project currently rendered, updated every render. The generation
  // alone is outrunnable: a stale A-closure (e.g. a mutation's follow-up
  // refresh) that STARTS after B's refresh claims a newer generation and
  // would win — so every commit is also bound to the project id captured
  // when the request began.
  const projectIdRef = useRef(project?.id)
  projectIdRef.current = project?.id

  const refresh = useCallback(async () => {
    const pid = project?.id
    if (!pid) return
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

  const run = useCallback(async (fn) => {
    // Same binding as refresh: a slow mutation for the previous project
    // must not flip busy/error state on the project now displayed (its
    // follow-up refresh is already id-bound and commits nothing).
    const pid = project?.id
    setBusy(true)
    setError(null)
    try {
      await fn()
      await refresh()
    } catch (err) {
      if (projectIdRef.current === pid) setError(err.message)
    } finally {
      if (projectIdRef.current === pid) setBusy(false)
    }
  }, [project?.id, refresh])

  const toggle = useCallback((path) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }, [])

  const pickUpload = useCallback((dir) => {
    uploadDirRef.current = dir
    fileInputRef.current?.click()
  }, [])

  const handleFilesPicked = useCallback(async (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = '' // allow re-picking the same file later
    if (files.length === 0) return
    const dir = uploadDirRef.current
    await run(async () => {
      for (const file of files) {
        try {
          await uploadProjectFile(project.id, file, { dir })
        } catch (err) {
          if (err.message === 'file already exists' &&
              window.confirm(`"${file.name}" already exists. Overwrite?`)) {
            await uploadProjectFile(project.id, file, { dir, overwrite: true })
          } else if (err.message !== 'file already exists') {
            throw err
          }
        }
      }
    })
    if (dir) setExpanded(prev => new Set(prev).add(dir))
  }, [project?.id, run])

  const handleNewFolder = useCallback(async (parentDir) => {
    const name = window.prompt('Folder name')
    if (!name || !name.trim()) return
    const path = parentDir ? `${parentDir}/${name.trim()}` : name.trim()
    await run(() => mkdirProjectPath(project.id, path))
    if (parentDir) setExpanded(prev => new Set(prev).add(parentDir))
  }, [project?.id, run])

  const handleRename = useCallback(async (node) => {
    const newPath = window.prompt('New path (relative to project root)', node.path)
    if (!newPath || !newPath.trim() || newPath.trim() === node.path) return
    await run(() => moveProjectPath(project.id, node.path, newPath.trim()))
  }, [project?.id, run])

  const handleDelete = useCallback(async (node) => {
    const label = node.type === 'dir' ? `folder "${node.path}" and everything in it` : `"${node.path}"`
    if (!window.confirm(`Delete ${label}?`)) return
    await run(() => deleteProjectPath(project.id, node.path))
  }, [project?.id, run])

  const handleDownload = useCallback(async (node) => {
    try {
      const url = await downloadProjectFile(project.id, node.path)
      const a = document.createElement('a')
      a.href = url
      a.download = node.name
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    }
  }, [project?.id])

  if (!project) {
    return (
      <div className="flex-1 flex items-center justify-center text-fg-subtle text-sm">
        Project not found
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-app">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        onChange={handleFilesPicked}
        className="hidden"
        data-testid="file-input"
      />
      {/* Header */}
      <div className="px-6 py-4 border-b border-border">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-folder-open text-amber-500/80"></i>
          <h1 className="text-lg font-semibold text-fg truncate">{project.name}</h1>
        </div>
        {project.description && (
          <p className="mt-1 text-sm text-fg-muted">{project.description}</p>
        )}
      </div>

      {/* Toolbar */}
      <div className="px-6 py-2 border-b border-border flex items-center gap-2">
        <button
          onClick={() => pickUpload('')}
          disabled={busy}
          className="px-3 py-1.5 bg-accent-strong hover:bg-accent-hover text-fg-inverse rounded-lg text-xs font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
        >
          <i className="fa-solid fa-file-arrow-up"></i>
          Upload files
        </button>
        <button
          onClick={() => handleNewFolder('')}
          disabled={busy}
          className="px-3 py-1.5 bg-surface hover:bg-surface-muted border border-border rounded-lg text-xs text-fg-muted transition-colors flex items-center gap-2 disabled:opacity-50"
        >
          <i className="fa-solid fa-folder-plus"></i>
          New folder
        </button>
        <button
          onClick={refresh}
          disabled={busy}
          className="ml-auto px-2 py-1.5 text-fg-subtle hover:text-fg text-xs disabled:opacity-50"
          title="Refresh" aria-label="Refresh file tree"
        >
          <i className="fa-solid fa-rotate-right"></i>
        </button>
      </div>

      {error && (
        <div className="mx-6 mt-3 px-3 py-2 bg-danger-subtle text-danger-fg rounded text-xs">
          {error}
        </div>
      )}

      {/* Tree */}
      <div className="flex-1 overflow-auto py-1">
        {tree.length === 0 && !error && (
          <div className="p-8 text-center text-xs text-fg-subtle">
            No files yet. Upload files or create a folder to get started.
          </div>
        )}
        {tree.map(node => (
          <NodeRow
            key={node.path}
            node={node}
            depth={0}
            expanded={expanded}
            onToggle={toggle}
            onUploadInto={pickUpload}
            onNewFolder={handleNewFolder}
            onRename={handleRename}
            onDelete={handleDelete}
            onDownload={handleDownload}
          />
        ))}
      </div>
    </div>
  )
}
