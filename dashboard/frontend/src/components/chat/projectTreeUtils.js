// Path/tree helpers shared by ProjectPage, ProjectExplorerPane and the
// tree row components. Kept free of JSX so react-refresh stays happy
// with projectTree.jsx exporting only components.

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
