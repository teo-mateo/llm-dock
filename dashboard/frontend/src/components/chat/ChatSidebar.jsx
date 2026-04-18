import { useState, useMemo } from 'react'

function ConversationItem({ conv, activeId, depth, confirmDelete, setConfirmDelete, onSelect, onDelete }) {
  const isSpinoff = !!conv.parent_conversation_id
  const icon = isSpinoff ? 'fa-code-branch' : 'fa-message'
  const iconColor = isSpinoff ? 'text-purple-400' : ''

  return (
    <div
      onClick={() => onSelect(conv.id)}
      className={`group flex items-center gap-2 py-2 cursor-pointer border-b border-gray-800/30 ${
        activeId === conv.id
          ? 'bg-gray-800 text-white'
          : 'text-gray-400 hover:bg-gray-800/50'
      }`}
      style={{ paddingLeft: `${12 + depth * 16}px`, paddingRight: 12 }}
    >
      <i className={`fa-solid ${icon} text-[10px] opacity-50 flex-shrink-0 ${iconColor}`}></i>
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
          className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 flex-shrink-0"
        >
          <i className="fa-solid fa-trash text-[10px]"></i>
        </button>
      )}
    </div>
  )
}

export default function ChatSidebar({ conversations, activeId, onSelect, onCreate, onDelete }) {
  const [confirmDelete, setConfirmDelete] = useState(null)

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

  function renderConv(conv, depth) {
    const children = tree.childrenMap[conv.id] || []
    return (
      <div key={conv.id}>
        <ConversationItem
          conv={conv}
          activeId={activeId}
          depth={depth}
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
