import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  getProjectFilesTree, uploadProjectFile, mkdirProjectPath,
  moveProjectPath, copyProjectPath, deleteProjectPath, downloadProjectFile,
} from '../../services/chat'
import ProjectFileEditor from './ProjectFileEditor'
import ContextMenu from './ContextMenu'
import {
  findNode, listDir, parentDir, baseName, isSelfOrDescendant, ancestorsOf,
} from './projectTreeUtils'
import { TreeFile, TreeDir } from './projectTree'

// The DataTransfer type carrying the dragged entry's project-relative
// path. A custom type keeps foreign drags (text, files from the OS) from
// being mistaken for an internal move.
const DND_TYPE = 'application/x-llmdock-path'

// First name that doesn't collide inside dirPath: "a.txt" -> "a (copy).txt"
// -> "a (copy 2).txt". Works off the client tree snapshot; a stale snapshot
// just means the backend's already_exists 409 surfaces as an error.
function uniqueChildName(tree, dirPath, name) {
  const siblings = new Set((listDir(tree, dirPath) || []).map(n => n.name))
  if (!siblings.has(name)) return name
  const dot = name.lastIndexOf('.')
  const stem = dot > 0 ? name.slice(0, dot) : name
  const ext = dot > 0 ? name.slice(dot) : ''
  for (let i = 1; i < 100; i++) {
    const candidate = i === 1 ? `${stem} (copy)${ext}` : `${stem} (copy ${i})${ext}`
    if (!siblings.has(candidate)) return candidate
  }
  return name // give up; the backend 409 will surface
}

function formatSize(bytes) {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function ProjectPage({ project, onEditorDirtyChange }) {
  const [tree, setTree] = useState([])
  // Tree-pane expansion state (dir paths). Root is always rendered.
  const [expanded, setExpanded] = useState(() => new Set())
  // Directory whose contents fill the right pane ('' = project root).
  const [selectedDir, setSelectedDir] = useState('')
  // {op: 'copy'|'cut', path, name} — armed by the context menu.
  const [clipboard, setClipboard] = useState(null)
  // {x, y, node} — node null means the right pane's background.
  const [menu, setMenu] = useState(null)
  // Dir path currently highlighted as a drag-and-drop target.
  const [dropTarget, setDropTarget] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  // {path, isNew} when the editor is open; replaces the right pane.
  const [editing, setEditing] = useState(null)
  // Local mirror of the editor's dirty state: the toolbar stays visible
  // while the editor is open, and starting another New file would remount
  // the keyed editor — an in-page replacement ChatPage's navigation guard
  // never sees. Guard it here.
  const editorDirtyRef = useRef(false)
  const handleEditorDirtyChange = useCallback((d) => {
    editorDirtyRef.current = d
    onEditorDirtyChange?.(d)
  }, [onEditorDirtyChange])
  const confirmDiscardEdits = useCallback(() => {
    if (!editing || !editorDirtyRef.current) return true
    return window.confirm('Discard unsaved changes?')
  }, [editing])
  // Mutations that touch the OPEN file or one of its ancestors (the tree
  // stays actionable while the editor is mounted) must not proceed behind
  // a dirty buffer's back: ask first, and let cancel abort the mutation.
  const editingUnder = useCallback((path) =>
    editing != null && isSelfOrDescendant(editing.path, path), [editing])
  const guardEditedPath = useCallback((srcPath) => {
    if (!editingUnder(srcPath)) return true
    if (!editorDirtyRef.current) return true
    return window.confirm('Discard unsaved changes?')
  }, [editingUnder])
  // The guard samples the buffer BEFORE the request, but the editor would
  // stay writable during the await — anything typed in that window would
  // be silently discarded by the post-success remount/close. So affected
  // mutations close the editor for the duration of the request (nothing
  // to type into) and reopen it afterwards: at the remapped path on
  // success, at the original path on failure.
  // Expansion state follows too: entries under the source move to the
  // destination (a remapped selection must not end up inside a collapsed
  // branch, and stale entries must not pre-expand a folder later
  // recreated at the old path), and the destination's ancestors open up
  // so the moved/renamed node is actually visible.
  const remapExpanded = useCallback((srcPath, dstPath) => {
    setExpanded(prev => {
      const next = new Set()
      for (const p of prev) {
        next.add(isSelfOrDescendant(p, srcPath) ? dstPath + p.slice(srcPath.length) : p)
      }
      for (const a of ancestorsOf(dstPath)) next.add(a)
      return next
    })
  }, [])
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
    // A stale closure (a previous project's mutation follow-up) must not
    // claim a generation at all — it would invalidate the CURRENT
    // project's in-flight fetch and strand the page empty.
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
    setSelectedDir('')
    setClipboard(null)
    setMenu(null)
    setDropTarget(null)
    setError(null)
    setBusy(false)
    setEditing(null)
    refresh()
  }, [refresh])

  // If the selected directory vanished (deleted, renamed, moved away),
  // fall back to its nearest surviving ancestor.
  useEffect(() => {
    if (!selectedDir) return
    let p = selectedDir
    while (p) {
      const node = findNode(tree, p)
      if (node && node.type === 'dir') break
      p = parentDir(p)
    }
    if (p !== selectedDir) setSelectedDir(p)
  }, [tree, selectedDir])

  // Returns true only when the mutation succeeded AND the component still
  // shows the project it ran against — callers use it to gate follow-up
  // state changes (selection/editor/expansion remaps, clipboard clears)
  // that must not happen when the backend rejected the operation, nor be
  // applied to a DIFFERENT project the user switched to mid-flight.
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
      return projectIdRef.current === pid
    } catch (err) {
      if (projectIdRef.current === pid) setError(err.message)
      return false
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

  const expandTo = useCallback((dirPath) => {
    if (!dirPath) return
    setExpanded(prev => {
      const next = new Set(prev)
      for (const a of ancestorsOf(dirPath)) next.add(a)
      next.add(dirPath)
      return next
    })
  }, [])

  const selectDir = useCallback((dirPath) => {
    if (editing) {
      if (!confirmDiscardEdits()) return
      setEditing(null)
    }
    setSelectedDir(dirPath)
    expandTo(dirPath)
  }, [editing, confirmDiscardEdits, expandTo])

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
          if (err.code === 'already_exists' &&
              window.confirm(`"${file.name}" already exists. Overwrite?`)) {
            await uploadProjectFile(project.id, file, { dir, overwrite: true })
          } else if (err.code !== 'already_exists') {
            throw err
          }
        }
      }
    })
  }, [project?.id, run])

  const handleNewFolder = useCallback(async (parentPath) => {
    const name = window.prompt('Folder name')
    if (!name || !name.trim()) return
    const path = parentPath ? `${parentPath}/${name.trim()}` : name.trim()
    const ok = await run(() => mkdirProjectPath(project.id, path))
    if (ok) expandTo(parentPath)
  }, [project?.id, run, expandTo])

  const handleRename = useCallback(async (node) => {
    const input = window.prompt('New path (relative to project root)', node.path)
    if (!input || !input.trim()) return
    // Normalize like the backend (split_rel_path strips slashes) so the
    // selection remap below works with the path the tree will report.
    const dst = input.trim().replace(/^\/+|\/+$/g, '')
    if (!dst || dst === node.path) return
    if (!guardEditedPath(node.path)) return
    const pid = project?.id
    const affectedEditing = editingUnder(node.path) ? editing : null
    if (affectedEditing) setEditing(null)
    const ok = await run(() => moveProjectPath(project.id, node.path, dst))
    if (!ok) {
      // Restore only when still on the same project — a mid-flight switch
      // already reset the editor state for the new project.
      if (affectedEditing && projectIdRef.current === pid) setEditing(affectedEditing)
      return
    }
    if (affectedEditing) {
      setEditing({ ...affectedEditing, path: dst + affectedEditing.path.slice(node.path.length) })
    }
    remapExpanded(node.path, dst)
    // Same remap as moveInto: a rename of the selected dir or one of its
    // ancestors must carry the selection to the new path, not strand it
    // on a path the refreshed tree no longer contains.
    setSelectedDir(prev => (prev && isSelfOrDescendant(prev, node.path)
      ? dst + prev.slice(node.path.length)
      : prev))
    setClipboard(prev => (prev && isSelfOrDescendant(prev.path, node.path) ? null : prev))
  }, [project?.id, run, guardEditedPath, editingUnder, editing, remapExpanded])

  const handleDelete = useCallback(async (node) => {
    if (!guardEditedPath(node.path)) return
    const label = node.type === 'dir' ? `folder "${node.path}" and everything in it` : `"${node.path}"`
    if (!window.confirm(`Delete ${label}?`)) return
    const pid = project?.id
    const affectedEditing = editingUnder(node.path) ? editing : null
    if (affectedEditing) setEditing(null) // closed before flight; stays closed on success
    const ok = await run(() => deleteProjectPath(project.id, node.path))
    if (!ok) {
      if (affectedEditing && projectIdRef.current === pid) setEditing(affectedEditing)
      return
    }
    setClipboard(prev => (prev && isSelfOrDescendant(prev.path, node.path) ? null : prev))
  }, [project?.id, run, guardEditedPath, editingUnder, editing])

  const handleOpenFile = useCallback((node) => {
    // Already open (e.g. clicking the highlighted tree row): a no-op.
    // Prompting would be misleading — confirming installs the same
    // editor key, so nothing is actually discarded.
    if (editing?.path === node.path) return
    if (!confirmDiscardEdits()) return
    setEditing({ path: node.path, isNew: false })
  }, [editing?.path, confirmDiscardEdits])

  const handleNewFile = useCallback((parentPath) => {
    if (!confirmDiscardEdits()) return
    const name = window.prompt('File name')
    if (!name || !name.trim()) return
    const path = parentPath ? `${parentPath}/${name.trim()}` : name.trim()
    // If it already exists, open it instead of silently overwriting on save.
    const existing = findNode(tree, path)
    setEditing({ path, isNew: !existing })
  }, [tree, confirmDiscardEdits])

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

  // -- Move (drag-and-drop and cut-paste share this) --

  const moveInto = useCallback(async (srcPath, dstDir) => {
    if (parentDir(srcPath) === dstDir) return // already there
    if (isSelfOrDescendant(dstDir, srcPath)) {
      setError('cannot move a folder into itself')
      return
    }
    const dstPath = dstDir ? `${dstDir}/${baseName(srcPath)}` : baseName(srcPath)
    if (!guardEditedPath(srcPath)) return
    const pid = project?.id
    const affectedEditing = editingUnder(srcPath) ? editing : null
    if (affectedEditing) setEditing(null)
    const ok = await run(() => moveProjectPath(project.id, srcPath, dstPath))
    if (!ok) {
      if (affectedEditing && projectIdRef.current === pid) setEditing(affectedEditing)
      return
    }
    if (affectedEditing) {
      setEditing({ ...affectedEditing, path: dstPath + affectedEditing.path.slice(srcPath.length) })
    }
    remapExpanded(srcPath, dstPath)
    // Keep the selection meaningful when the selected dir itself moved.
    setSelectedDir(prev => {
      if (prev && isSelfOrDescendant(prev, srcPath)) {
        return dstPath + prev.slice(srcPath.length)
      }
      return prev
    })
    setClipboard(prev => (prev && isSelfOrDescendant(prev.path, srcPath) ? null : prev))
    expandTo(dstDir)
  }, [project?.id, run, expandTo, guardEditedPath, editingUnder, editing, remapExpanded])

  // -- Clipboard --

  const armClipboard = useCallback((op, node) => {
    setClipboard({ op, path: node.path, name: node.name })
  }, [])

  const handlePaste = useCallback(async (dstDir) => {
    if (!clipboard) return
    const { op, path, name } = clipboard
    if (op === 'cut') {
      await moveInto(path, dstDir)
    } else {
      const dstName = uniqueChildName(tree, dstDir, name)
      const dstPath = dstDir ? `${dstDir}/${dstName}` : dstName
      if (isSelfOrDescendant(dstDir, path)) {
        setError('cannot copy a folder into itself')
        return
      }
      const ok = await run(() => copyProjectPath(project.id, path, dstPath))
      if (ok) expandTo(dstDir)
    }
  }, [clipboard, tree, moveInto, run, project?.id, expandTo])

  // -- Drag and drop --

  const handleDragStart = useCallback((e, node) => {
    e.dataTransfer.setData(DND_TYPE, node.path)
    e.dataTransfer.effectAllowed = 'move'
  }, [])

  const handleDragOver = useCallback((e, dirPath) => {
    if (!e.dataTransfer.types.includes(DND_TYPE)) return
    e.preventDefault()
    e.stopPropagation()
    e.dataTransfer.dropEffect = 'move'
    setDropTarget(dirPath)
  }, [])

  const handleDragLeave = useCallback((dirPath) => {
    setDropTarget(prev => (prev === dirPath ? null : prev))
  }, [])

  const handleDrop = useCallback((e, dirPath) => {
    e.preventDefault()
    e.stopPropagation()
    setDropTarget(null)
    const srcPath = e.dataTransfer.getData(DND_TYPE)
    if (srcPath) moveInto(srcPath, dirPath)
  }, [moveInto])

  // -- Context menu --

  const openMenu = useCallback((e, node) => {
    e.preventDefault()
    e.stopPropagation()
    setMenu({ x: e.clientX, y: e.clientY, node })
  }, [])

  const closeMenu = useCallback(() => setMenu(null), [])

  const menuItems = useMemo(() => {
    if (!menu) return []
    const node = menu.node
    if (!node || node.isRoot) {
      // Background of the right pane acts on the selected directory; the
      // root tree node acts on the project root.
      const dir = node?.isRoot ? '' : selectedDir
      return [
        { label: 'New file', icon: 'fa-file-circle-plus', onClick: () => handleNewFile(dir) },
        { label: 'New folder', icon: 'fa-folder-plus', onClick: () => handleNewFolder(dir) },
        { label: 'Upload files', icon: 'fa-file-arrow-up', onClick: () => pickUpload(dir) },
        'sep',
        { label: 'Paste', icon: 'fa-paste', disabled: !clipboard, onClick: () => handlePaste(dir) },
      ]
    }
    const isDir = node.type === 'dir'
    const items = []
    if (isDir) {
      items.push({ label: 'Open', icon: 'fa-folder-open', onClick: () => selectDir(node.path) })
      items.push({ label: 'Paste into', icon: 'fa-paste', disabled: !clipboard, onClick: () => handlePaste(node.path) })
    } else {
      items.push({ label: 'Open', icon: 'fa-pen-to-square', onClick: () => handleOpenFile(node) })
      items.push({ label: 'Download', icon: 'fa-download', onClick: () => handleDownload(node) })
    }
    items.push('sep')
    items.push({ label: 'Cut', icon: 'fa-scissors', onClick: () => armClipboard('cut', node) })
    items.push({ label: 'Copy', icon: 'fa-copy', onClick: () => armClipboard('copy', node) })
    items.push({ label: 'Rename', icon: 'fa-pen', onClick: () => handleRename(node) })
    items.push('sep')
    items.push({ label: 'Delete', icon: 'fa-trash', danger: true, onClick: () => handleDelete(node) })
    return items
  }, [menu, clipboard, selectedDir, handleNewFile, handleNewFolder, pickUpload, handlePaste,
      selectDir, handleOpenFile, handleDownload, armClipboard, handleRename, handleDelete])

  const entries = listDir(tree, selectedDir) || []
  const crumbs = selectedDir ? selectedDir.split('/') : []
  const cutPath = clipboard?.op === 'cut' ? clipboard.path : null

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
          onClick={() => pickUpload(selectedDir)}
          disabled={busy}
          className="px-3 py-1.5 bg-accent-strong hover:bg-accent-hover text-fg-inverse rounded-lg text-xs font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
        >
          <i className="fa-solid fa-file-arrow-up"></i>
          Upload files
        </button>
        <button
          onClick={() => handleNewFile(selectedDir)}
          disabled={busy}
          className="px-3 py-1.5 bg-surface hover:bg-surface-muted border border-border rounded-lg text-xs text-fg-muted transition-colors flex items-center gap-2 disabled:opacity-50"
        >
          <i className="fa-solid fa-file-circle-plus"></i>
          New file
        </button>
        <button
          onClick={() => handleNewFolder(selectedDir)}
          disabled={busy}
          className="px-3 py-1.5 bg-surface hover:bg-surface-muted border border-border rounded-lg text-xs text-fg-muted transition-colors flex items-center gap-2 disabled:opacity-50"
        >
          <i className="fa-solid fa-folder-plus"></i>
          New folder
        </button>
        {clipboard && (
          <span className="flex items-center gap-1.5 px-2 py-1 bg-surface border border-border rounded-lg text-[11px] text-fg-subtle" data-testid="clipboard-chip">
            <i className={`fa-solid ${clipboard.op === 'cut' ? 'fa-scissors' : 'fa-copy'} text-[10px]`}></i>
            <span className="max-w-[160px] truncate">{clipboard.name}</span>
            <button
              onClick={() => setClipboard(null)}
              className="text-fg-faint hover:text-fg cursor-pointer"
              aria-label="Clear clipboard"
            ><i className="fa-solid fa-xmark text-[10px]"></i></button>
          </span>
        )}
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

      <div className="flex-1 flex overflow-hidden">
        {/* Left: folder tree */}
        <div className="w-56 flex-shrink-0 border-r border-border overflow-y-auto py-2 px-1.5 select-none">
          <div
            onClick={() => selectDir('')}
            onContextMenu={e => openMenu(e, { isRoot: true })}
            onDragOver={e => handleDragOver(e, '')}
            onDragLeave={() => handleDragLeave('')}
            onDrop={e => handleDrop(e, '')}
            className={`flex items-center gap-1.5 py-1 pl-2 pr-2 text-sm cursor-pointer rounded ${
              selectedDir === '' ? 'bg-accent-subtle text-fg' : 'text-fg-muted hover:bg-surface-muted'
            } ${dropTarget === '' ? 'ring-1 ring-accent-strong bg-accent-subtle' : ''}`}
            data-testid="tree-node-root"
          >
            <i className="fa-solid fa-house text-xs text-fg-subtle flex-shrink-0"></i>
            <span className="flex-1 min-w-0 truncate font-medium">{project.name}</span>
          </div>
          {tree.map(node => (
            node.type === 'dir' ? (
              <TreeDir
                key={node.path}
                node={node}
                depth={1}
                expanded={expanded}
                selectedDir={selectedDir}
                editingPath={editing?.path}
                dropTarget={dropTarget}
                cutPath={cutPath}
                onToggle={toggle}
                onSelect={selectDir}
                onOpenFile={handleOpenFile}
                onMenu={openMenu}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              />
            ) : (
              <TreeFile
                key={node.path}
                node={node}
                depth={1}
                editingPath={editing?.path}
                cutPath={cutPath}
                onOpen={handleOpenFile}
                onMenu={openMenu}
                onDragStart={handleDragStart}
              />
            )
          ))}
        </div>

        {/* Right: editor, or the selected directory's contents */}
        {editing ? (
          <ProjectFileEditor
            key={`${project.id}:${editing.path}`}
            projectId={project.id}
            path={editing.path}
            isNew={editing.isNew}
            onDirtyChange={handleEditorDirtyChange}
            onClose={() => setEditing(null)}
            onSaved={() => {
              // A saved new file now exists on disk; drop the isNew flag so
              // later saves carry the conflict guard, and refresh the tree.
              setEditing(prev => (prev ? { ...prev, isNew: false } : prev))
              refresh()
            }}
          />
        ) : (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Breadcrumb */}
          <div className="px-4 py-1.5 border-b border-border-subtle flex items-center gap-1 text-xs text-fg-subtle flex-wrap">
            <button
              onClick={() => selectDir('')}
              className="hover:text-fg cursor-pointer"
              aria-label="Go to project root"
            ><i className="fa-solid fa-house"></i></button>
            {crumbs.map((seg, i) => {
              const path = crumbs.slice(0, i + 1).join('/')
              return (
                <span key={path} className="flex items-center gap-1">
                  <i className="fa-solid fa-chevron-right text-[8px] text-fg-faint"></i>
                  <button
                    onClick={() => selectDir(path)}
                    className={`hover:text-fg cursor-pointer ${i === crumbs.length - 1 ? 'text-fg font-medium' : ''}`}
                    data-testid={`crumb-${path}`}
                  >{seg}</button>
                </span>
              )
            })}
          </div>

          <div
            className={`flex-1 overflow-auto py-1 ${dropTarget === `bg:${selectedDir}` ? 'ring-1 ring-inset ring-accent-strong' : ''}`}
            onContextMenu={e => openMenu(e, null)}
            onDragOver={e => handleDragOver(e, `bg:${selectedDir}`)}
            onDragLeave={() => handleDragLeave(`bg:${selectedDir}`)}
            onDrop={e => handleDrop(e, selectedDir)}
            data-testid="dir-contents"
          >
            {entries.length === 0 && !error && (
              <div className="p-8 text-center text-xs text-fg-subtle">
                {selectedDir ? 'This folder is empty.' : 'No files yet. Upload files or create a folder to get started.'}
              </div>
            )}
            {entries.map(node => {
              const isDir = node.type === 'dir'
              return (
                <div
                  key={node.path}
                  draggable
                  onClick={isDir ? () => selectDir(node.path) : () => handleOpenFile(node)}
                  onContextMenu={e => openMenu(e, node)}
                  onDragStart={e => handleDragStart(e, node)}
                  onDragOver={isDir ? e => handleDragOver(e, node.path) : undefined}
                  onDragLeave={isDir ? () => handleDragLeave(node.path) : undefined}
                  onDrop={isDir ? e => handleDrop(e, node.path) : undefined}
                  className={`group flex items-center gap-2 py-1.5 px-4 border-b border-border-subtle text-sm cursor-pointer ${
                    isDir ? 'text-fg' : 'text-fg-muted'
                  } hover:bg-surface-muted ${dropTarget === node.path ? 'ring-1 ring-accent-strong bg-accent-subtle' : ''} ${
                    cutPath && isSelfOrDescendant(node.path, cutPath) ? 'opacity-50' : ''
                  }`}
                  data-testid={`file-row-${node.path}`}
                >
                  <i className={`${isDir ? 'fa-solid fa-folder text-amber-500/80' : 'fa-regular fa-file text-fg-faint'} text-xs flex-shrink-0 w-4`}></i>
                  <span className="flex-1 min-w-0 truncate">{node.name}</span>
                  {!isDir && <span className="text-[10px] text-fg-faint flex-shrink-0">{formatSize(node.size)}</span>}
                  <span className="flex items-center gap-0.5 flex-shrink-0">
                    {!isDir && (
                      <button
                        onClick={e => { e.stopPropagation(); handleDownload(node) }}
                        className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-fg p-1 cursor-pointer"
                        title="Download" aria-label={`Download ${node.path}`}
                      ><i className="fa-solid fa-download text-xs"></i></button>
                    )}
                    <button
                      onClick={e => { e.stopPropagation(); handleRename(node) }}
                      className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-fg p-1 cursor-pointer"
                      title="Rename / move" aria-label={`Rename ${node.path}`}
                    ><i className="fa-solid fa-pen text-xs"></i></button>
                    <button
                      onClick={e => { e.stopPropagation(); handleDelete(node) }}
                      className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-danger-fg p-1 cursor-pointer"
                      title="Delete" aria-label={`Delete ${node.path}`}
                    ><i className="fa-solid fa-trash text-xs"></i></button>
                  </span>
                </div>
              )
            })}
          </div>
        </div>
        )}
      </div>

      {menu && <ContextMenu x={menu.x} y={menu.y} items={menuItems} onClose={closeMenu} />}
    </div>
  )
}
