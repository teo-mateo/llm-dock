// Project file-tree primitives shared by ProjectPage (full explorer) and
// ProjectExplorerPane (the strip shown next to a project conversation).

export function findNode(nodes, path) {
  for (const n of nodes) {
    if (n.path === path) return n
    if (n.type === 'dir' && n.children) {
      const hit = findNode(n.children, path)
      if (hit) return hit
    }
  }
  return null
}

// Children of a directory path ('' = project root).
export function listDir(tree, dirPath) {
  if (!dirPath) return tree
  const node = findNode(tree, dirPath)
  return node && node.type === 'dir' ? (node.children || []) : null
}

export function parentDir(path) {
  const i = path.lastIndexOf('/')
  return i === -1 ? '' : path.slice(0, i)
}

export function baseName(path) {
  return path.split('/').pop()
}

export function isSelfOrDescendant(dirPath, ofPath) {
  return dirPath === ofPath || dirPath.startsWith(ofPath + '/')
}

// All ancestor dir paths of a path, root ('') excluded:
// 'a/b/c' -> ['a', 'a/b'].
export function ancestorsOf(path) {
  const out = []
  const parts = path.split('/')
  for (let i = 1; i < parts.length; i++) out.push(parts.slice(0, i).join('/'))
  return out
}

// One file row in a tree pane. Files aren't drop targets (drops go to
// folders), but they are drag sources and carry the full context menu.
// Drag-and-drop and context-menu handlers are optional — a read-mostly
// pane simply omits them.
export function TreeFile({ node, depth, editingPath, cutPath, onOpen, onMenu, onDragStart }) {
  return (
    <div
      draggable={!!onDragStart}
      onClick={() => onOpen(node)}
      onContextMenu={onMenu ? e => onMenu(e, node) : undefined}
      onDragStart={onDragStart ? e => onDragStart(e, node) : undefined}
      className={`flex items-center gap-1.5 py-1 pr-2 text-sm cursor-pointer rounded ${
        editingPath === node.path ? 'bg-accent-subtle text-fg' : 'text-fg-muted hover:bg-surface-muted'
      } ${cutPath && isSelfOrDescendant(node.path, cutPath) ? 'opacity-50' : ''}`}
      style={{ paddingLeft: `${8 + depth * 14}px` }}
      data-testid={`tree-node-${node.path}`}
    >
      <span className="w-4 flex-shrink-0"></span>
      <i className="fa-regular fa-file text-xs text-fg-faint flex-shrink-0"></i>
      <span className="flex-1 min-w-0 truncate">{node.name}</span>
    </div>
  )
}

// One folder row in a tree pane (recursive over children; the backend
// sorts dirs before files, so children render in tree order). When
// onSelect is omitted (read-mostly pane), clicking the row toggles
// expansion instead of selecting the directory.
export function TreeDir({ node, depth, expanded, selectedDir, editingPath, dropTarget, cutPath,
                          onToggle, onSelect, onOpenFile, onMenu, onDragStart, onDragOver, onDragLeave, onDrop }) {
  const children = node.children || []
  const isExpanded = expanded.has(node.path)
  return (
    <>
      <div
        draggable={!!onDragStart}
        onClick={() => (onSelect ? onSelect(node.path) : onToggle(node.path))}
        onContextMenu={onMenu ? e => onMenu(e, node) : undefined}
        onDragStart={onDragStart ? e => onDragStart(e, node) : undefined}
        onDragOver={onDragOver ? e => onDragOver(e, node.path) : undefined}
        onDragLeave={onDragLeave ? () => onDragLeave(node.path) : undefined}
        onDrop={onDrop ? e => onDrop(e, node.path) : undefined}
        className={`flex items-center gap-1.5 py-1 pr-2 text-sm cursor-pointer rounded ${
          selectedDir === node.path ? 'bg-accent-subtle text-fg' : 'text-fg-muted hover:bg-surface-muted'
        } ${dropTarget === node.path ? 'ring-1 ring-accent-strong bg-accent-subtle' : ''} ${
          cutPath && isSelfOrDescendant(node.path, cutPath) ? 'opacity-50' : ''
        }`}
        style={{ paddingLeft: `${8 + depth * 14}px` }}
        data-testid={`tree-node-${node.path}`}
      >
        <button
          onClick={e => { e.stopPropagation(); onToggle(node.path) }}
          className={`w-4 flex-shrink-0 text-fg-faint cursor-pointer ${children.length ? '' : 'invisible'}`}
          aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${node.path}`}
          tabIndex={-1}
        >
          <i className={`fa-solid fa-chevron-${isExpanded ? 'down' : 'right'} text-[9px]`}></i>
        </button>
        <i className={`fa-solid fa-folder${selectedDir === node.path ? '-open' : ''} text-xs text-amber-500/80 flex-shrink-0`}></i>
        <span className="flex-1 min-w-0 truncate">{node.name}</span>
      </div>
      {isExpanded && children.map(child => (
        child.type === 'dir' ? (
          <TreeDir
            key={child.path}
            node={child}
            depth={depth + 1}
            expanded={expanded}
            selectedDir={selectedDir}
            editingPath={editingPath}
            dropTarget={dropTarget}
            cutPath={cutPath}
            onToggle={onToggle}
            onSelect={onSelect}
            onOpenFile={onOpenFile}
            onMenu={onMenu}
            onDragStart={onDragStart}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
          />
        ) : (
          <TreeFile
            key={child.path}
            node={child}
            depth={depth + 1}
            editingPath={editingPath}
            cutPath={cutPath}
            onOpen={onOpenFile}
            onMenu={onMenu}
            onDragStart={onDragStart}
          />
        )
      ))}
    </>
  )
}
