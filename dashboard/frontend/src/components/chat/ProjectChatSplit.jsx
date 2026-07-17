import { useState, useEffect, useCallback, useRef } from 'react'
import ProjectExplorerPane from './ProjectExplorerPane'
import ProjectFileEditor from './ProjectFileEditor'

const WIDTH_KEY = 'llmdock.chatExplorer.width'
const COLLAPSED_KEY = 'llmdock.chatExplorer.collapsed'

const MIN_WIDTH = 160
const MAX_FRACTION = 0.45

function readStoredWidth() {
  try {
    const v = parseInt(localStorage.getItem(WIDTH_KEY), 10)
    return Number.isFinite(v) && v >= MIN_WIDTH ? v : null
  } catch {
    return null
  }
}

function readStoredCollapsed() {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === 'true'
  } catch {
    return false
  }
}

// Splits the conversation area when the conversation belongs to a project:
// a resizable file-explorer strip on the left (20% by default), the chat
// (children) on the right. Without a project it renders the chat alone.
// Opening a file from the strip overlays the editor on the chat region so
// the conversation stays loaded underneath.
export default function ProjectChatSplit({ project, conversationId, refreshKey = 0, onEditorDirtyChange, children }) {
  const [collapsed, setCollapsed] = useState(readStoredCollapsed)
  // null = never resized: the strip uses the 20% default until the first
  // drag pins a pixel width.
  const [width, setWidth] = useState(readStoredWidth)
  const [dragging, setDragging] = useState(false)
  // {path, isNew} when the editor overlay is open.
  const [editing, setEditing] = useState(null)
  // Editor saves bump this so the pane re-reads the tree (a saved new
  // file must appear); combined with the parent's refreshKey.
  const [savedBump, setSavedBump] = useState(0)
  const containerRef = useRef(null)
  const dirtyRef = useRef(false)

  const projectId = project?.id

  // ChatPage passes onEditorDirtyChange as a fresh inline function every
  // render. Hold it behind a ref so notifyDirty stays identity-stable —
  // otherwise the editor-reset effect below would re-fire on every parent
  // rerender (each streaming delta!) and silently unmount a dirty editor
  // (codex iteration 1, P1).
  const onDirtyRef = useRef(onEditorDirtyChange)
  useEffect(() => { onDirtyRef.current = onEditorDirtyChange }, [onEditorDirtyChange])
  const notifyDirty = useCallback((d) => {
    dirtyRef.current = d
    onDirtyRef.current?.(d)
  }, [])

  // Switching conversation (or project) closes the overlay. The dirty
  // guard for that navigation lives in ChatPage (confirmDiscardEdits),
  // which fires before the route changes — by the time this effect runs
  // the discard is already confirmed.
  useEffect(() => {
    setEditing(null)
    notifyDirty(false)
  }, [conversationId, projectId, notifyDirty])

  useEffect(() => {
    try { localStorage.setItem(COLLAPSED_KEY, String(collapsed)) } catch { /* ignore */ }
  }, [collapsed])

  useEffect(() => {
    if (width == null) return
    try { localStorage.setItem(WIDTH_KEY, String(width)) } catch { /* ignore */ }
  }, [width])

  // Divider drag: window-level listeners while dragging, clamped to
  // [MIN_WIDTH, 45% of the split container].
  useEffect(() => {
    if (!dragging) return
    const onMove = (e) => {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const max = Math.max(MIN_WIDTH, Math.floor(rect.width * MAX_FRACTION))
      setWidth(Math.min(Math.max(e.clientX - rect.left, MIN_WIDTH), max))
    }
    const onUp = () => setDragging(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [dragging])

  const handleOpenFile = useCallback((path, isNew) => {
    // Re-clicking the open file is a no-op (nothing would be discarded —
    // confirming just remounts the same editor).
    if (editing?.path === path) return
    if (editing && dirtyRef.current && !window.confirm('Discard unsaved changes?')) return
    notifyDirty(false)
    setEditing({ path, isNew })
  }, [editing, notifyDirty])

  const handleCloseEditor = useCallback(() => {
    setEditing(null)
    notifyDirty(false)
  }, [notifyDirty])

  if (!project) return children

  return (
    <div ref={containerRef} className="flex-1 flex overflow-hidden min-w-0" data-testid="project-chat-split">
      {collapsed ? (
        <div className="w-8 flex-shrink-0 border-r border-border bg-app flex flex-col items-center py-2">
          <button
            onClick={() => setCollapsed(false)}
            className="text-fg-subtle hover:text-fg p-1.5 cursor-pointer"
            title={`Show ${project.name} files`}
            aria-label="Show file explorer"
          >
            <i className="fa-solid fa-angles-right text-xs"></i>
          </button>
          <i className="fa-solid fa-folder text-xs text-amber-500/50 mt-2" title={project.name}></i>
        </div>
      ) : (
        <>
          <div
            className="flex-shrink-0 border-r border-border overflow-hidden"
            style={{ width: width != null ? `${width}px` : '20%', minWidth: `${MIN_WIDTH}px` }}
            data-testid="explorer-strip"
          >
            <ProjectExplorerPane
              project={project}
              refreshKey={refreshKey + savedBump}
              editingPath={editing?.path ?? null}
              onOpenFile={handleOpenFile}
              onCollapse={() => setCollapsed(true)}
            />
          </div>
          <div
            onMouseDown={(e) => { e.preventDefault(); setDragging(true) }}
            className={`w-1.5 flex-shrink-0 cursor-col-resize -ml-1 z-10 ${
              dragging ? 'bg-accent-strong/40' : 'hover:bg-accent-strong/30'
            }`}
            title="Drag to resize"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize file explorer"
            data-testid="explorer-divider"
          ></div>
        </>
      )}

      <div className="flex-1 flex min-w-0 relative">
        {children}
        {editing && (
          <div className="absolute inset-0 z-30 bg-app flex" data-testid="editor-overlay">
            <ProjectFileEditor
              key={`${project.id}:${editing.path}`}
              projectId={project.id}
              path={editing.path}
              isNew={editing.isNew}
              onDirtyChange={notifyDirty}
              onClose={handleCloseEditor}
              onSaved={() => {
                setEditing(prev => (prev ? { ...prev, isNew: false } : prev))
                setSavedBump(b => b + 1)
              }}
            />
          </div>
        )}
        {/* Transparent shield so mousemove keeps flowing during a drag even
            over iframes/artifacts rendered inside the chat. */}
        {dragging && <div className="absolute inset-0 z-40 cursor-col-resize"></div>}
      </div>
    </div>
  )
}
