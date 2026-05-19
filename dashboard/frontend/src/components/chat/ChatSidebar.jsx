import { useState, useMemo } from 'react'

function ConversationItem({ conv, activeId, depth, selectMode, selected, onToggleSelect, confirmDelete, setConfirmDelete, onSelect, onDelete }) {
  const isSpinoff = !!conv.parent_conversation_id

  // Spinoffs keep their branch icon and swap to a checkbox on hover; main
  // conversations show the checkbox permanently.
  const checkboxShown = selectMode || selected
  const spinoffIconVisibilityClass = checkboxShown ? 'opacity-0' : 'group-hover/iconslot:opacity-0'
  const spinoffCheckboxVisibilityClass = checkboxShown ? 'opacity-100' : 'opacity-0 group-hover/iconslot:opacity-100'

  return (
    <div
      onClick={() => onSelect(conv.id)}
      className={`group flex items-center gap-2 py-2 cursor-pointer border-b border-gray-800/30 ${
        selected
          ? 'bg-blue-900/30 text-white'
          : activeId === conv.id
            ? 'bg-gray-800 text-white'
            : 'text-gray-400 hover:bg-gray-800/50'
      }`}
      style={{ paddingLeft: `${12 + depth * 16}px`, paddingRight: 12 }}
    >
      {isSpinoff ? (
        <label
          className="group/iconslot relative w-8 h-8 -m-2 flex items-center justify-center flex-shrink-0 cursor-pointer"
          onClick={e => e.stopPropagation()}
        >
          <i
            className={`fa-solid fa-code-branch text-[10px] opacity-50 text-purple-400 absolute inset-0 flex items-center justify-center transition-opacity pointer-events-none ${spinoffIconVisibilityClass}`}
          ></i>
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(conv.id)}
            className={`w-3.5 h-3.5 accent-blue-500 cursor-pointer transition-opacity ${spinoffCheckboxVisibilityClass}`}
            title="Select"
          />
        </label>
      ) : (
        <label
          className="group/iconslot relative w-8 h-8 -m-2 flex items-center justify-center flex-shrink-0 cursor-pointer"
          onClick={e => e.stopPropagation()}
        >
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(conv.id)}
            className={`w-3.5 h-3.5 accent-blue-500 cursor-pointer transition-opacity ${
              checkboxShown ? 'opacity-100' : 'opacity-0 group-hover/iconslot:opacity-100'
            }`}
            title="Select"
          />
        </label>
      )}
      <div className="flex-1 min-w-0">
        <div className="text-sm truncate">{conv.title}</div>
        <div className="text-[10px] text-gray-600">
          {new Date(conv.updated_at).toLocaleDateString()}
        </div>
      </div>
      {confirmDelete === conv.id ? (
        <div className="flex gap-1 flex-shrink-0">
          <button
            onClick={e => { e.stopPropagation(); onDelete(conv.id); setConfirmDelete(null) }}
            className="text-[10px] px-1.5 py-0.5 bg-red-600 rounded text-white"
          >Yes</button>
          <button
            onClick={e => { e.stopPropagation(); setConfirmDelete(null) }}
            className="text-[10px] px-1.5 py-0.5 bg-gray-600 rounded text-white"
          >No</button>
        </div>
      ) : (
        <button
          onClick={e => { e.stopPropagation(); setConfirmDelete(conv.id) }}
          className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 flex-shrink-0 p-1.5 -m-1.5 cursor-pointer"
          title="Delete conversation"
          aria-label="Delete conversation"
        >
          <i className="fa-solid fa-trash text-xs"></i>
        </button>
      )}
    </div>
  )
}

export default function ChatSidebar({ conversations, activeId, onSelect, onCreate, onDelete, onDeleteMany }) {
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [confirmBulk, setConfirmBulk] = useState(false)

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

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const clearSelection = () => {
    setSelectedIds(new Set())
    setConfirmBulk(false)
  }

  const handleBulkDelete = async () => {
    const ids = Array.from(selectedIds)
    clearSelection()
    if (onDeleteMany) await onDeleteMany(ids)
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
        />
        {children.map(child => renderConv(child, depth + 1))}
      </div>
    )
  }

  return (
    <div className="w-72 border-r border-gray-800 flex flex-col bg-gray-900 flex-shrink-0">
      {/* Header */}
      <div className="p-3 border-b border-gray-800">
        <button
          onClick={onCreate}
          className="w-full px-3 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2"
        >
          <i className="fa-solid fa-plus"></i>
          New Conversation
        </button>
      </div>

      {/* Always-visible header row: shows count + select-all in browse mode,
          morphs to selection toolbar in select mode. Same outer div / height
          either way so the conversation list never shifts vertically. */}
      <div
        className={`h-9 px-3 border-b border-gray-800 flex items-center justify-between text-xs ${
          selectionCount > 0 ? 'bg-gray-800/60' : ''
        }`}
      >
        {selectionCount === 0 ? (
          <>
            <span className="text-gray-500">
              {conversations.length} {conversations.length === 1 ? 'chat' : 'chats'}
            </span>
            {tree.roots.length > 0 && (
              <button
                onClick={toggleSelectAllRoots}
                className="text-[11px] text-gray-500 hover:text-gray-300"
                title="Selects only top-level conversations; spin-offs follow their parent"
              >
                {allRootsSelected ? 'Deselect all' : 'Select all'}
              </button>
            )}
          </>
        ) : (
          <>
            <span className="text-gray-300">{selectionCount} selected</span>
            <div className="flex items-center gap-2">
              {confirmBulk ? (
                <>
                  <button
                    onClick={handleBulkDelete}
                    className="px-2 py-1 bg-red-600 hover:bg-red-500 rounded text-white"
                  >Delete {selectionCount}</button>
                  <button
                    onClick={() => setConfirmBulk(false)}
                    className="px-2 py-1 bg-gray-600 hover:bg-gray-500 rounded text-white"
                  >Cancel</button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => setConfirmBulk(true)}
                    className="px-2 py-1 text-red-400 hover:text-red-300 hover:bg-red-900/30 rounded"
                    title="Delete selected"
                  >
                    <i className="fa-solid fa-trash"></i>
                  </button>
                  <button
                    onClick={clearSelection}
                    className="px-2 py-1 text-gray-400 hover:text-gray-200"
                    title="Clear selection"
                  >Clear</button>
                </>
              )}
            </div>
          </>
        )}
      </div>

      {/* Conversation tree */}
      <div className="flex-1 overflow-auto">
        {conversations.length === 0 && (
          <div className="p-4 text-center text-xs text-gray-500">
            No conversations yet
          </div>
        )}
        {tree.roots.map(conv => renderConv(conv, 0))}
      </div>
    </div>
  )
}
