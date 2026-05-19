import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'

const STORAGE_KEY = 'llmdock.sidebar.collapsed'

function readCollapsed() {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    // Default collapsed (issue #29 §2) when nothing stored.
    return v === null ? true : v === 'true'
  } catch {
    return true
  }
}

const NAV_ITEMS = [
  { to: '/', end: true, icon: 'fa-server', label: 'Services' },
  { to: '/chat', end: false, icon: 'fa-comments', label: 'Chat' },
  { to: '/tools', end: false, icon: 'fa-toolbox', label: 'Tools' },
]

function Sidebar() {
  const [collapsed, setCollapsed] = useState(readCollapsed)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(collapsed))
    } catch {
      /* localStorage unavailable — keep in-memory state only */
    }
  }, [collapsed])

  return (
    <aside
      className={`hidden md:flex ${
        collapsed ? 'w-16' : 'w-56'
      } bg-app border-r border-border-subtle flex-col flex-shrink-0 transition-[width] duration-200 ease-in-out`}
    >
      {/* Logo + collapse toggle */}
      <div
        className={`h-16 border-b border-border-subtle flex items-center ${
          collapsed ? 'justify-center px-0' : 'justify-between px-4'
        }`}
      >
        {!collapsed && (
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center flex-shrink-0">
              <i className="fa-solid fa-cube text-white text-sm"></i>
            </div>
            <div className="min-w-0">
              <h1 className="font-bold text-lg truncate text-fg">LLM-Dock</h1>
              <p className="text-xs text-fg-subtle">v1.0.0</p>
            </div>
          </div>
        )}
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="w-8 h-8 flex items-center justify-center rounded-lg text-fg-muted hover:text-fg hover:bg-surface/60 transition-colors"
        >
          <i
            className={`fa-solid ${
              collapsed ? 'fa-angles-right' : 'fa-angles-left'
            } text-sm`}
          ></i>
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4">
        {NAV_ITEMS.map(({ to, end, icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              `group/nav relative flex items-center gap-3 py-2.5 ${
                collapsed ? 'justify-center px-0' : 'px-4'
              } ${
                isActive
                  ? 'text-fg bg-surface-strong/70'
                  : 'text-fg-muted hover:bg-surface/50'
              }`
            }
          >
            <i className={`fa-solid ${icon} w-5 text-center`}></i>
            {!collapsed && <span>{label}</span>}
            {collapsed && (
              <span
                role="tooltip"
                className="pointer-events-none absolute left-full ml-2 z-20 whitespace-nowrap rounded-md bg-surface px-2 py-1 text-xs text-fg border border-border opacity-0 shadow-lg transition-opacity duration-150 group-hover/nav:opacity-100"
              >
                {label}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User section */}
      <div
        className={`border-t border-border-subtle ${
          collapsed ? 'p-2' : 'p-4'
        }`}
      >
        <div
          className={`flex items-center ${
            collapsed ? 'justify-center' : 'gap-3'
          }`}
        >
          <div
            className="w-8 h-8 bg-surface-strong rounded-full flex items-center justify-center flex-shrink-0"
            title={collapsed ? 'Admin' : undefined}
          >
            <i className="fa-solid fa-user text-fg-muted text-sm"></i>
          </div>
          {!collapsed && (
            <>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate text-fg">Admin</p>
              </div>
              <button
                className="text-fg-subtle hover:text-fg-muted"
                aria-label="Log out"
                title="Log out"
              >
                <i className="fa-solid fa-right-from-bracket"></i>
              </button>
            </>
          )}
        </div>
      </div>
    </aside>
  )
}

export default Sidebar
