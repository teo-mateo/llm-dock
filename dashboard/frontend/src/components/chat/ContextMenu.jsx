import { useEffect, useRef } from 'react'

// Generic right-click menu. `items` is a list of
// {label, icon, onClick, disabled?, danger?} entries or the string 'sep'.
// The caller owns positioning (x/y from the contextmenu event) and closes
// the menu via onClose — this component only handles dismissal (click
// away, Escape, window blur) and viewport clamping.
export default function ContextMenu({ x, y, items, onClose }) {
  const ref = useRef(null)

  useEffect(() => {
    const away = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose()
    }
    const esc = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('mousedown', away)
    window.addEventListener('contextmenu', away)
    window.addEventListener('keydown', esc)
    window.addEventListener('blur', onClose)
    return () => {
      window.removeEventListener('mousedown', away)
      window.removeEventListener('contextmenu', away)
      window.removeEventListener('keydown', esc)
      window.removeEventListener('blur', onClose)
    }
  }, [onClose])

  // Rough clamp so the menu never opens half off-screen. Row height ~32px.
  const width = 200
  const height = items.length * 32 + 12
  const left = Math.max(0, Math.min(x, (window.innerWidth || 10000) - width))
  const top = Math.max(0, Math.min(y, (window.innerHeight || 10000) - height))

  return (
    <div
      ref={ref}
      className="fixed z-50 min-w-[190px] bg-surface border border-border rounded-lg shadow-xl py-1"
      style={{ left, top }}
      data-testid="context-menu"
      role="menu"
    >
      {items.map((item, i) =>
        item === 'sep' ? (
          <div key={i} className="my-1 border-t border-border-subtle" />
        ) : (
          <button
            key={i}
            role="menuitem"
            disabled={item.disabled}
            onClick={() => { onClose(); item.onClick() }}
            className={`w-full flex items-center gap-2.5 px-3 py-1.5 text-left text-sm cursor-pointer disabled:opacity-40 disabled:cursor-default ${
              item.danger
                ? 'text-danger-fg hover:bg-danger-subtle'
                : 'text-fg hover:bg-surface-muted'
            } disabled:hover:bg-transparent`}
          >
            <i className={`fa-solid ${item.icon} w-4 text-xs text-fg-subtle`}></i>
            <span className="flex-1">{item.label}</span>
            {item.hint && <span className="text-[10px] text-fg-faint">{item.hint}</span>}
          </button>
        )
      )}
    </div>
  )
}
