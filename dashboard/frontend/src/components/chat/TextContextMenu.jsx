import { useState, useEffect, useCallback } from 'react'

// Copies text to the clipboard. Falls back to a hidden textarea +
// execCommand for insecure origins (HTTP through the tunnel) where
// navigator.clipboard is unavailable. Mirrors the pattern in
// CopyablePre.jsx.
async function copyToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return true } catch { /* fall through */ }
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try { ok = document.execCommand('copy') } catch { ok = false }
  document.body.removeChild(ta)
  return ok
}

export default function TextContextMenu({ onSpinoff, onQuote, onCritique }) {
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
      <button
        onClick={async () => {
          await copyToClipboard(menu.text)
          setMenu(null)
        }}
        className="w-full text-left px-3 py-2 text-sm text-gray-200 hover:bg-gray-700 flex items-center gap-2"
      >
        <i className="fa-solid fa-copy text-gray-400 text-xs"></i>
        Copy
      </button>
      <button
        onClick={() => {
          onQuote?.(menu.text)
          setMenu(null)
        }}
        className="w-full text-left px-3 py-2 text-sm text-gray-200 hover:bg-gray-700 flex items-center gap-2"
      >
        <i className="fa-solid fa-quote-right text-blue-400 text-xs"></i>
        Quote in reply
      </button>
      <button
        onClick={() => {
          onCritique?.(menu.text)
          setMenu(null)
        }}
        className="w-full text-left px-3 py-2 text-sm text-gray-200 hover:bg-gray-700 flex items-center gap-2"
      >
        <i className="fa-solid fa-magnifying-glass text-amber-400 text-xs"></i>
        Critique this
      </button>
    </div>
  )
}
