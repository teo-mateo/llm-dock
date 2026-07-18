import { useState, useEffect, useMemo, useRef } from 'react'

function ConversationItem({ conv, activeId, depth, selectMode, selected, onToggleSelect, confirmDelete, setConfirmDelete, onSelect, onDelete, renaming, onRenameStart, onRenameConfirm }) {
  const isSpinoff = !!conv.parent_conversation_id
  const inputRef = useRef(null)

  useEffect(() => {
    if (renaming === conv.id) {
      inputRef.current?.focus()
    }
  }, [renaming, conv.id])

  const checkboxShown = selectMode || selected
  const spinoffIconVisibilityClass = checkboxShown ? 'opacity-0' : 'group-hover/iconslot:opacity-0'
  const spinoffCheckboxVisibilityClass = checkboxShown ? 'opacity-100' : 'opacity-0 group-hover/iconslot:opacity-100'

  const handleRenameSubmit = (e) => {
    e.preventDefault()
    const val = inputRef.current?.value?.trim()
    if (val && val !== conv.title) {
      onRenameConfirm(conv.id, val)
    } else {
      onRenameConfirm(conv.id, null)
    }
  }

  const handleRenameBlur = () => {
    requestAnimationFrame(() => {
      if (document.activeElement === inputRef.current) return
      const val = inputRef.current?.value?.trim()
      if (val && val !== conv.title) {
        onRenameConfirm(conv.id, val)
      } else {
        onRenameConfirm(conv.id, null)
      }
    })
  }

  return (
    <div
      onClick={() => onSelect(conv.id)}
      className={`group flex items-center gap-2 py-2 cursor-pointer border-b border-border-subtle ${
        selected
          ? 'bg-accent-subtle text-fg'
          : activeId === conv.id
            ? 'bg-surface text-fg'
            : 'text-fg-muted hover:bg-surface-muted'
      }`}
      style={{ paddingLeft: `${12 + depth * 16}px`, paddingRight: 12 }}
    >
      {/* Drive the toggle from the label's click rather than the nested
          <input>'s. The label is a 32px hit target wrapping a 14px
          checkbox; clicks on the surrounding padding reach the input
          only via the browser's label-activation synthetic click, whose
          modifier-key state is not guaranteed to mirror the original
          mouse event. Reading shiftKey from the label click — and
          preventDefault-ing so the synthetic input toggle never fires —
          keeps the full hit target consistent with the visible checkbox
          (PR #48 codex iter 2). Direct clicks on the input must NOT be
          canceled — a canceled click makes the browser revert the native
          checked toggle after React has already committed checked=true,
          desyncing the visible box from selection state — so the input
          handles its own click (stopPropagation keeps the label handler
          out of it). */}
      {isSpinoff ? (
        <label
          className="group/iconslot relative w-8 h-8 -m-2 flex items-center justify-center flex-shrink-0 cursor-pointer"
          onClick={e => { e.preventDefault(); e.stopPropagation(); onToggleSelect(conv.id, e.shiftKey) }}
        >
          <i
            className={`fa-solid fa-code-branch text-[10px] opacity-50 text-purple-400 absolute inset-0 flex items-center justify-center transition-opacity pointer-events-none ${spinoffIconVisibilityClass}`}
          ></i>
          <input
            type="checkbox"
            checked={selected}
            onChange={() => {}}
            onClick={e => { e.stopPropagation(); onToggleSelect(conv.id, e.shiftKey) }}
            className={`w-3.5 h-3.5 accent-accent cursor-pointer transition-opacity ${spinoffCheckboxVisibilityClass}`}
            title="Select"
          />
        </label>
      ) : (
        <label
          className="group/iconslot relative w-8 h-8 -m-2 flex items-center justify-center flex-shrink-0 cursor-pointer"
          onClick={e => { e.preventDefault(); e.stopPropagation(); onToggleSelect(conv.id, e.shiftKey) }}
        >
          <input
            type="checkbox"
            checked={selected}
            onChange={() => {}}
            onClick={e => { e.stopPropagation(); onToggleSelect(conv.id, e.shiftKey) }}
            className={`w-3.5 h-3.5 accent-accent cursor-pointer transition-opacity ${
              checkboxShown ? 'opacity-100' : 'opacity-0 group-hover/iconslot:opacity-100'
            }`}
            title="Select"
          />
        </label>
      )}
      <div className="flex-1 min-w-0">
        {renaming === conv.id ? (
          <form onSubmit={handleRenameSubmit} className="flex items-center gap-1.5">
            <input
              ref={inputRef}
              type="text"
              defaultValue={conv.title}
              onBlur={handleRenameBlur}
              onKeyDown={e => {
                if (e.key === 'Enter') { e.preventDefault(); handleRenameSubmit(e) }
                if (e.key === 'Escape') onRenameConfirm(conv.id, null)
              }}
              className="flex-1 min-w-0 bg-surface-strong border border-border-strong rounded px-2 py-0.5 text-sm text-fg focus:outline-none focus:border-accent"
            />
          </form>
        ) : (
          <>
            <div className="text-sm flex items-center gap-1.5 min-w-0">
              {conv.active_run && (conv.active_run.status === 'running' || conv.active_run.status === 'queued') && (
                <i
                  className={`fa-solid fa-circle-notch fa-spin text-[10px] flex-shrink-0 ${
                    conv.active_run.status === 'running' ? 'text-accent' : 'text-fg-faint'
                  }`}
                  title={conv.active_run.status === 'running' ? 'Generating…' : 'Queued…'}
                  aria-label={conv.active_run.status === 'running' ? 'Run in progress' : 'Run queued'}
                  data-testid="active-run-indicator"
                ></i>
              )}
              <span className="truncate">{conv.title}</span>
            </div>
            <div className="text-[10px] text-fg-faint">
              {new Date(conv.updated_at).toLocaleDateString()}
            </div>
          </>
        )}
      </div>
      {confirmDelete === conv.id ? (
        <div className="flex gap-1 flex-shrink-0">
          <button
            onClick={e => { e.stopPropagation(); onDelete(conv.id); setConfirmDelete(null) }}
            className="text-[10px] px-1.5 py-0.5 bg-danger rounded text-white"
          >Yes</button>
          <button
            onClick={e => { e.stopPropagation(); setConfirmDelete(null) }}
            className="text-[10px] px-1.5 py-0.5 bg-surface-strong rounded text-fg"
          >No</button>
        </div>
      ) : renaming === conv.id ? (
        <div className="flex gap-1 flex-shrink-0">
          <button
            onClick={e => { e.stopPropagation(); handleRenameSubmit(e) }}
            className="text-success-fg hover:text-success-fg flex-shrink-0 p-1.5 -m-1.5 cursor-pointer"
            title="Confirm rename"
            aria-label="Confirm rename"
          >
            <i className="fa-solid fa-check text-xs"></i>
          </button>
          <button
            onClick={e => { e.stopPropagation(); onRenameConfirm(conv.id, null) }}
            className="text-fg-muted hover:text-fg flex-shrink-0 p-1.5 -m-1.5 cursor-pointer"
            title="Cancel rename"
            aria-label="Cancel rename"
          >
            <i className="fa-solid fa-xmark text-xs"></i>
          </button>
        </div>
      ) : (
        <>
          <button
            onClick={e => { e.stopPropagation(); onRenameStart(conv.id) }}
            className={`opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-fg flex-shrink-0 p-1.5 -m-1.5 cursor-pointer ${selectMode ? 'pointer-events-none opacity-0' : ''}`}
            title="Rename conversation"
            aria-label="Rename conversation"
          >
            <i className="fa-solid fa-pen text-xs"></i>
          </button>
          <button
            onClick={e => { e.stopPropagation(); setConfirmDelete(conv.id) }}
            className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-danger-fg flex-shrink-0 p-1.5 -m-1.5 cursor-pointer"
            title="Delete conversation"
            aria-label="Delete conversation"
          >
            <i className="fa-solid fa-trash text-xs"></i>
          </button>
        </>
      )}
    </div>
  )
}

function ProjectHeader({ project, collapsed, active, onToggleCollapse, onOpenProject, onCreateInProject, confirmDeleteProject, setConfirmDeleteProject, onDeleteProject, renamingProject, onRenameProjectStart, onRenameProjectConfirm, count }) {
  const inputRef = useRef(null)

  useEffect(() => {
    if (renamingProject === project.id) {
      inputRef.current?.focus()
    }
  }, [renamingProject, project.id])

  const handleRenameSubmit = (e) => {
    e.preventDefault()
    const val = inputRef.current?.value?.trim()
    if (val && val !== project.name) {
      onRenameProjectConfirm(project.id, val)
    } else {
      onRenameProjectConfirm(project.id, null)
    }
  }

  const handleRenameBlur = () => {
    requestAnimationFrame(() => {
      if (document.activeElement === inputRef.current) return
      const val = inputRef.current?.value?.trim()
      if (val && val !== project.name) {
        onRenameProjectConfirm(project.id, val)
      } else {
        onRenameProjectConfirm(project.id, null)
      }
    })
  }

  return (
    <div
      onClick={() => onToggleCollapse(project.id)}
      className={`group flex items-center gap-2 py-2 px-3 cursor-pointer border-b border-border-subtle ${
        active ? 'bg-surface text-fg' : 'bg-surface-muted/50 text-fg-muted hover:bg-surface-muted'
      }`}
      data-testid={`project-header-${project.id}`}
    >
      <i className={`fa-solid fa-chevron-${collapsed ? 'right' : 'down'} text-[9px] w-3 flex-shrink-0 text-fg-faint`}></i>
      <i className="fa-solid fa-folder text-xs flex-shrink-0 text-amber-500/80"></i>
      <div className="flex-1 min-w-0">
        {renamingProject === project.id ? (
          <form onSubmit={handleRenameSubmit} onClick={e => e.stopPropagation()} className="flex items-center gap-1.5">
            <input
              ref={inputRef}
              type="text"
              defaultValue={project.name}
              onBlur={handleRenameBlur}
              onKeyDown={e => {
                if (e.key === 'Enter') { e.preventDefault(); handleRenameSubmit(e) }
                if (e.key === 'Escape') onRenameProjectConfirm(project.id, null)
              }}
              className="flex-1 min-w-0 bg-surface-strong border border-border-strong rounded px-2 py-0.5 text-sm text-fg focus:outline-none focus:border-accent"
            />
          </form>
        ) : (
          <span className="text-sm font-medium truncate flex items-center gap-1.5">
            <span className="truncate">{project.name}</span>
            <span className="text-[10px] text-fg-faint flex-shrink-0">{count}</span>
          </span>
        )}
      </div>
      {confirmDeleteProject === project.id ? (
        <div className="flex gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
          <button
            onClick={() => { onDeleteProject(project.id); setConfirmDeleteProject(null) }}
            className="text-[10px] px-1.5 py-0.5 bg-danger rounded text-white"
          >Yes</button>
          <button
            onClick={() => setConfirmDeleteProject(null)}
            className="text-[10px] px-1.5 py-0.5 bg-surface-strong rounded text-fg"
          >No</button>
        </div>
      ) : renamingProject === project.id ? null : (
        <>
          {onOpenProject && (
            <button
              onClick={e => { e.stopPropagation(); onOpenProject(project.id) }}
              className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-fg flex-shrink-0 p-1.5 -m-1.5 cursor-pointer"
              title="Open project files"
              aria-label="Open project files"
            >
              <i className="fa-solid fa-folder-open text-xs"></i>
            </button>
          )}
          <button
            onClick={e => { e.stopPropagation(); onCreateInProject(project.id) }}
            className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-fg flex-shrink-0 p-1.5 -m-1.5 cursor-pointer"
            title="New conversation in project"
            aria-label="New conversation in project"
          >
            <i className="fa-solid fa-plus text-xs"></i>
          </button>
          <button
            onClick={e => { e.stopPropagation(); onRenameProjectStart(project.id) }}
            className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-fg flex-shrink-0 p-1.5 -m-1.5 cursor-pointer"
            title="Rename project"
            aria-label="Rename project"
          >
            <i className="fa-solid fa-pen text-xs"></i>
          </button>
          <button
            onClick={e => { e.stopPropagation(); setConfirmDeleteProject(project.id) }}
            className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-danger-fg flex-shrink-0 p-1.5 -m-1.5 cursor-pointer"
            title="Delete project (conversations are kept)"
            aria-label="Delete project"
          >
            <i className="fa-solid fa-trash text-xs"></i>
          </button>
        </>
      )}
    </div>
  )
}

export default function ChatSidebar({ onCollapse, conversations, activeId, onSelect, onCreate, onDelete, onDeleteMany, onRename, projects = [], activeProjectId = null, onOpenProject, onCreateProject, onRenameProject, onDeleteProject, onCreateInProject, onMoveMany }) {
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [renaming, setRenaming] = useState(null)
  const [confirmDeleteProject, setConfirmDeleteProject] = useState(null)
  const [renamingProject, setRenamingProject] = useState(null)
  const [collapsedProjects, setCollapsedProjects] = useState(() => new Set())
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [confirmBulk, setConfirmBulk] = useState(false)
  // Anchor for shift-click range selection. Holds the id of the last
  // checkbox toggled without shift; a subsequent shift-click selects the
  // span between anchor and clicked id in render order.
  const anchorIdRef = useRef(null)

  // Build tree: top-level conversations + their children
  const tree = useMemo(() => {
    const roots = conversations.filter(c => !c.parent_conversation_id)
    const childrenMap = {}
    for (const c of conversations) {
      if (c.parent_conversation_id) {
        if (!childrenMap[c.parent_conversation_id]) childrenMap[c.parent_conversation_id] = []
        childrenMap[c.parent_conversation_id].push(c)
      }
    }
    return { roots, childrenMap }
  }, [conversations])

  // Group ROOT conversations by project. Spinoffs always render under
  // their parent (via childrenMap) regardless of their own project_id, so
  // only roots are bucketed. Roots pointing at an unknown project (e.g.
  // deleted in another tab) fall back to unfiled rather than vanishing.
  const grouped = useMemo(() => {
    const knownIds = new Set(projects.map(p => p.id))
    const byProject = new Map(projects.map(p => [p.id, []]))
    const unfiled = []
    for (const c of tree.roots) {
      if (c.project_id && knownIds.has(c.project_id)) {
        byProject.get(c.project_id).push(c)
      } else {
        unfiled.push(c)
      }
    }
    return { byProject, unfiled }
  }, [tree, projects])

  // Flat list of VISIBLE conversation ids in render order (projects first,
  // each root followed by its descendants depth-first, then unfiled roots).
  // Collapsed projects contribute nothing — a shift-click range must never
  // select rows the user can't see. Used to resolve the [anchor, clicked]
  // span for shift-click range selection.
  const flatOrder = useMemo(() => {
    const out = []
    const walk = (id) => {
      out.push(id)
      for (const child of tree.childrenMap[id] || []) walk(child.id)
    }
    for (const p of projects) {
      if (collapsedProjects.has(p.id)) continue
      for (const root of grouped.byProject.get(p.id) || []) walk(root.id)
    }
    for (const root of grouped.unfiled) walk(root.id)
    return out
  }, [tree, projects, grouped, collapsedProjects])

  const toggleSelect = (id, shiftKey) => {
    const anchor = anchorIdRef.current
    if (shiftKey && anchor && anchor !== id) {
      const ai = flatOrder.indexOf(anchor)
      const ci = flatOrder.indexOf(id)
      if (ai !== -1 && ci !== -1) {
        const [lo, hi] = ai < ci ? [ai, ci] : [ci, ai]
        const range = flatOrder.slice(lo, hi + 1)
        setSelectedIds(prev => {
          const next = new Set(prev)
          for (const rid of range) next.add(rid)
          return next
        })
        // Leave anchor alone so subsequent shift-clicks extend from the
        // same origin (standard finder/gmail behavior).
        return
      }
    }
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
    anchorIdRef.current = id
  }

  const clearSelection = () => {
    setSelectedIds(new Set())
    setConfirmBulk(false)
    anchorIdRef.current = null
  }

  const handleBulkDelete = async () => {
    const ids = Array.from(selectedIds)
    clearSelection()
    if (onDeleteMany) await onDeleteMany(ids)
  }

  const handleRenameStart = (id) => {
    setRenaming(id)
  }

  const handleRenameConfirm = async (id, newTitle) => {
    setRenaming(null)
    if (newTitle && onRename) await onRename(id, newTitle)
  }

  const handleRenameProjectConfirm = async (id, newName) => {
    setRenamingProject(null)
    if (newName && onRenameProject) await onRenameProject(id, newName)
  }

  const toggleCollapse = (projectId) => {
    setCollapsedProjects(prev => {
      const next = new Set(prev)
      if (next.has(projectId)) next.delete(projectId)
      else next.add(projectId)
      return next
    })
  }

  const handleBulkMove = async (targetProjectId) => {
    // Membership is root-only (spin-offs always render under — and follow —
    // their root), so resolve every selected id to its root before moving:
    // moving a spin-off moves the tree the user actually sees. The Set also
    // dedupes a selection that contains both a root and its descendants.
    const byId = new Map(conversations.map(c => [c.id, c]))
    const rootIds = new Set()
    for (const id of selectedIds) {
      let cursor = id
      while (byId.get(cursor)?.parent_conversation_id) {
        cursor = byId.get(cursor).parent_conversation_id
      }
      rootIds.add(cursor)
    }
    clearSelection()
    if (onMoveMany) await onMoveMany(Array.from(rootIds), targetProjectId)
  }

  const selectionCount = selectedIds.size
  // Once anything is selected, every row swaps its icon for a checkbox.
  const selectMode = selectionCount > 0

  const allRootsSelected = tree.roots.length > 0 && tree.roots.every(c => selectedIds.has(c.id))

  const toggleSelectAllRoots = () => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (allRootsSelected) {
        for (const c of tree.roots) next.delete(c.id)
      } else {
        for (const c of tree.roots) next.add(c.id)
      }
      return next
    })
  }

  function renderConv(conv, depth) {
    const children = tree.childrenMap[conv.id] || []
    return (
      <div key={conv.id}>
        <ConversationItem
          conv={conv}
          activeId={activeId}
          depth={depth}
          selectMode={selectMode}
          selected={selectedIds.has(conv.id)}
          onToggleSelect={toggleSelect}
          confirmDelete={confirmDelete}
          setConfirmDelete={setConfirmDelete}
          onSelect={onSelect}
          onDelete={onDelete}
          renaming={renaming}
          onRenameStart={handleRenameStart}
          onRenameConfirm={handleRenameConfirm}
        />
        {children.map(child => renderConv(child, depth + 1))}
      </div>
    )
  }

  return (
    <div className="w-full border-r border-border flex flex-col bg-app flex-shrink-0 h-full">
      {/* Title bar */}
      <div className="px-3 py-2 border-b border-border flex items-center gap-2 flex-shrink-0">
        <i className="fa-solid fa-message text-xs text-blue-400/80 flex-shrink-0"></i>
        <span className="flex-1 min-w-0 truncate text-xs font-semibold text-fg uppercase tracking-wide">
          Conversations
        </span>
        <button
          onClick={onCollapse}
          className="text-fg-subtle hover:text-fg p-1 -m-1 cursor-pointer"
          title="Hide conversations"
          aria-label="Hide conversations"
        >
          <i className="fa-solid fa-angles-left text-sm"></i>
        </button>
      </div>

      {/* Actions */}
      <div className="p-3 border-b border-border">
        <button
          onClick={onCreate}
          className="w-full px-3 py-2 bg-accent-strong hover:bg-accent-hover text-fg-inverse rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
        >
          <i className="fa-solid fa-plus"></i>
          New Conversation
        </button>
        {onCreateProject && (
          <button
            onClick={onCreateProject}
            className="w-full mt-2 px-3 py-1.5 bg-surface hover:bg-surface-muted border border-border rounded-lg text-xs text-fg-muted transition-colors flex items-center justify-center gap-2"
          >
            <i className="fa-solid fa-folder-plus"></i>
            New Project
          </button>
        )}
      </div>

      {/* Always-visible header row: shows count + select-all in browse mode,
          morphs to selection toolbar in select mode. Same outer div / height
          either way so the conversation list never shifts vertically. */}
      <div
        className={`h-9 px-3 border-b border-border flex items-center justify-between text-xs ${
          selectionCount > 0 ? 'bg-surface-muted' : ''
        }`}
      >
        {selectionCount === 0 ? (
          <>
            <span className="text-fg-subtle">
              {conversations.length} {conversations.length === 1 ? 'chat' : 'chats'}
            </span>
            {tree.roots.length > 0 && (
              <button
                onClick={toggleSelectAllRoots}
                className="text-[11px] text-fg-subtle hover:text-fg-muted"
                title="Selects only top-level conversations; spin-offs follow their parent"
              >
                {allRootsSelected ? 'Deselect all' : 'Select all'}
              </button>
            )}
          </>
        ) : (
          <>
            <span className="text-fg-muted">{selectionCount} selected</span>
            <div className="flex items-center gap-2">
              {confirmBulk ? (
                <>
                  <button
                    onClick={handleBulkDelete}
                    className="px-2 py-1 bg-danger hover:bg-danger rounded text-white"
                  >Delete {selectionCount}</button>
                  <button
                    onClick={() => setConfirmBulk(false)}
                    className="px-2 py-1 bg-surface-strong hover:bg-surface-strong rounded text-fg"
                  >Cancel</button>
                </>
              ) : (
                <>
                  {onMoveMany && projects.length > 0 && (
                    <select
                      value=""
                      onChange={e => {
                        const v = e.target.value
                        if (!v) return
                        handleBulkMove(v === '__none__' ? null : v)
                      }}
                      onClick={e => e.stopPropagation()}
                      className="max-w-24 bg-surface border border-border rounded px-1 py-0.5 text-[11px] text-fg-muted cursor-pointer"
                      title="Move selected to project"
                      aria-label="Move selected to project"
                    >
                      <option value="" disabled>Move to…</option>
                      {projects.map(p => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                      <option value="__none__">No project</option>
                    </select>
                  )}
                  <button
                    onClick={() => setConfirmBulk(true)}
                    className="px-2 py-1 text-danger-fg hover:text-danger-fg hover:bg-danger-subtle rounded"
                    title="Delete selected"
                  >
                    <i className="fa-solid fa-trash"></i>
                  </button>
                  <button
                    onClick={clearSelection}
                    className="px-2 py-1 text-fg-muted hover:text-fg"
                    title="Clear selection"
                  >Clear</button>
                </>
              )}
            </div>
          </>
        )}
      </div>

      {/* Conversation tree: project sections first, then unfiled chats */}
      <div className="flex-1 overflow-auto">
        {conversations.length === 0 && projects.length === 0 && (
          <div className="p-4 text-center text-xs text-fg-subtle">
            No conversations yet
          </div>
        )}
        {projects.map(project => {
          const roots = grouped.byProject.get(project.id) || []
          const collapsed = collapsedProjects.has(project.id)
          // The server-side count is authoritative — if it disagrees with
          // the loaded rows (e.g. a page was dropped), never claim the
          // project is empty.
          const count = Math.max(project.conversation_count ?? 0, roots.length)
          return (
            <div key={project.id}>
              <ProjectHeader
                project={project}
                count={count}
                collapsed={collapsed}
                active={activeProjectId === project.id}
                onToggleCollapse={toggleCollapse}
                onOpenProject={onOpenProject}
                onCreateInProject={onCreateInProject}
                confirmDeleteProject={confirmDeleteProject}
                setConfirmDeleteProject={setConfirmDeleteProject}
                onDeleteProject={onDeleteProject}
                renamingProject={renamingProject}
                onRenameProjectStart={setRenamingProject}
                onRenameProjectConfirm={handleRenameProjectConfirm}
              />
              {!collapsed && roots.map(conv => renderConv(conv, 1))}
              {!collapsed && roots.length === 0 && count === 0 && (
                <div className="py-2 pl-8 pr-3 text-[11px] text-fg-faint border-b border-border-subtle">
                  Empty project
                </div>
              )}
              {!collapsed && roots.length === 0 && count > 0 && (
                <div className="py-2 pl-8 pr-3 text-[11px] text-fg-faint border-b border-border-subtle">
                  {count} conversation{count === 1 ? '' : 's'} not loaded
                </div>
              )}
            </div>
          )
        })}
        {grouped.unfiled.map(conv => renderConv(conv, 0))}
      </div>
    </div>
  )
}
