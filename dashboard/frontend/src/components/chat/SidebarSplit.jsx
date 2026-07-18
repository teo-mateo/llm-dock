import { useState, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react'
import ChatSidebar from './ChatSidebar'
import useResizableWidth from '../../hooks/useResizableWidth'

const COLLAPSED_KEY = 'llmdock.chatSidebar.collapsed'
const WIDTH_KEY = 'llmdock.chatSidebar.width'
const MIN_WIDTH = 200
const MAX_FRACTION = 0.35
const DEFAULT_WIDTH = 288

function readCollapsed() {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === 'true'
  } catch {
    return false
  }
}

const SidebarSplit = forwardRef(function SidebarSplit({ children, ...sidebarProps }, ref) {
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const { containerRef, currentWidth, dragging, startDrag, setCurrentWidth } = useResizableWidth({
    storageKey: WIDTH_KEY,
    minWidth: MIN_WIDTH,
    maxFraction: MAX_FRACTION,
    defaultWidthPx: DEFAULT_WIDTH,
  })

  useImperativeHandle(ref, () => ({
    adjustWidth: (delta) => {
      const el = containerRef.current
      if (!el) return
      const max = Math.max(MIN_WIDTH, Math.floor(el.getBoundingClientRect().width * MAX_FRACTION))
      setCurrentWidth(prev => Math.min(Math.max(prev + delta, MIN_WIDTH), max))
    },
    toggleCollapse: () => setCollapsed(prev => !prev),
  }), [setCurrentWidth, containerRef])

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED_KEY, String(collapsed))
    } catch {
      /* ignore */
    }
  }, [collapsed])

  const handleCollapse = useCallback(() => setCollapsed(true), [])
  const handleExpand = useCallback(() => setCollapsed(false), [])

  return (
    <div ref={containerRef} className="flex-1 flex overflow-hidden">
      {collapsed && (
        <div className="w-10 flex-shrink-0 border-r border-border flex flex-col items-center bg-app">
          <div className="h-16 w-full border-b border-border-subtle flex items-center justify-center flex-shrink-0">
            <button
              onClick={handleExpand}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-fg-muted hover:text-fg hover:bg-surface/60 transition-colors cursor-pointer"
              title="Show conversations"
              aria-label="Show conversations"
              aria-expanded={false}
            >
              <i className="fa-solid fa-angles-right text-sm"></i>
            </button>
          </div>
          <div className="py-4 overflow-hidden w-full flex items-center justify-center">
            <button
              onClick={handleExpand}
              className="text-[10px] font-semibold text-fg-subtle hover:text-fg uppercase tracking-widest cursor-pointer"
              style={{ writingMode: 'vertical-lr', transform: 'rotate(180deg)' }}
              title="Show conversations"
            >
              Conversations
            </button>
          </div>
        </div>
      )}
      <div
        className="flex-shrink-0"
        style={{
          display: collapsed ? 'none' : undefined,
          width: `${currentWidth}px`,
          minWidth: `${MIN_WIDTH}px`,
        }}
      >
        <ChatSidebar
          collapsed={collapsed}
          onCollapse={handleCollapse}
          onExpand={handleExpand}
          {...sidebarProps}
        />
      </div>
      {!collapsed && (
        <div
          onMouseDown={startDrag}
          className={`w-1.5 flex-shrink-0 cursor-col-resize -ml-1 z-10 ${
            dragging ? 'bg-accent-strong/40' : 'hover:bg-accent-strong/30'
          }`}
          title="Drag to resize"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize sidebar"
        ></div>
      )}
      <div className="flex-1 flex min-w-0 relative">
        {children}
        {dragging && <div className="absolute inset-0 z-40 cursor-col-resize"></div>}
      </div>
    </div>
  )
})

export default SidebarSplit
