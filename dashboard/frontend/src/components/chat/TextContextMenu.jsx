import { useState, useEffect, useCallback } from 'react'

export default function TextContextMenu({ onSpinoff }) {
  const [menu, setMenu] = useState(null) // { x, y, text }

  const handleContextMenu = useCallback((e) => {
    const selection = window.getSelection()
    const text = selection?.toString().trim()
    if (!text) return // no text selected, let browser default handle it

    e.preventDefault()
    setMenu({ x: e.clientX, y: e.clientY, text })
  }, [])

  useEffect(() => {
    document.addEventListener('contextmenu', handleContextMenu)
    return () => document.removeEventListener('contextmenu', handleContextMenu)
  }, [handleContextMenu])

  // Close menu on any click or scroll
  useEffect(() => {
    if (!menu) return
    function close() { setMenu(null) }
    window.addEventListener('click', close)
    window.addEventListener('scroll', close, true)
    return () => {
      window.removeEventListener('click', close)
      window.removeEventListener('scroll', close, true)
    }
  }, [menu])

  if (!menu) return null

  return (
    <div
      className="fixed z-50 bg-gray-800 border border-gray-600 rounded-lg shadow-xl py-1 min-w-[160px]"
      style={{ left: menu.x, top: menu.y }}
      onClick={e => e.stopPropagation()}
    >
      <button
        onClick={() => {
          onSpinoff(menu.text)
          setMenu(null)
        }}
        className="w-full text-left px-3 py-2 text-sm text-gray-200 hover:bg-gray-700 flex items-center gap-2"
      >
        <i className="fa-solid fa-code-branch text-purple-400 text-xs"></i>
        Spin off...
      </button>
    </div>
  )
}
