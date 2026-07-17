import { useState, useEffect, useLayoutEffect, useCallback, useRef } from 'react'
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

  // A stored width is only known to fit the display it was saved on. Track
  // the container's current 45% bound and clamp at render — otherwise a
  // width persisted on a wide window swallows the whole split (and the
  // chat) after the window narrows, until the next drag.
  const [maxWidth, setMaxWidth] = useState(null)
  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const measure = () => {
      const w = el.getBoundingClientRect().width
      if (w > 0) setMaxWidth(Math.max(MIN_WIDTH, Math.floor(w * MAX_FRACTION)))
    }
    measure()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
    // Re-attach when the split appears: with no project there IS no
    // container, and the ref is still null on that first pass.
  }, [projectId])
  const shownWidth = width != null && maxWidth != null ? Math.min(width, maxWidth) : width

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
      {collapsed && (
        // Same geometry as the other collapsed rails (main Sidebar,
        // ChatSidebar): h-16 bordered header, w-8 h-8 toggle, text-sm
        // icon — the expander chevrons of all collapsed panels line up.
        <div className="w-10 flex-shrink-0 border-r border-border bg-app flex flex-col items-center">
          <div className="h-16 w-full border-b border-border-subtle flex items-center justify-center flex-shrink-0">
            <button
              onClick={() => setCollapsed(false)}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-fg-muted hover:text-fg hover:bg-surface/60 transition-colors cursor-pointer"
              title={`Show ${project.name} files`}
              aria-label="Show file explorer"
            >
              <i className="fa-solid fa-angles-right text-sm"></i>
            </button>
          </div>
          <div className="py-4">
            <i className="fa-solid fa-folder text-sm text-amber-500/50" title={project.name}></i>
          </div>
        </div>
      )}
      {/* The pane stays MOUNTED while collapsed (display:none) so an
          in-flight upload keeps its state alive and its follow-up
          refresh lands in the tree the user sees on re-expand (codex
          iteration 3, P2). */}
      <div
        className="flex-shrink-0 border-r border-border overflow-hidden"
        style={{
          display: collapsed ? 'none' : undefined,
          width: shownWidth != null ? `${shownWidth}px` : '20%',
          minWidth: `${MIN_WIDTH}px`,
        }}
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
      {!collapsed && (
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
