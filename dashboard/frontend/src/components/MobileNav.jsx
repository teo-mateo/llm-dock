import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { NAV_ITEMS } from './navItems'
import ThemeSwitcher from './ThemeSwitcher'

// md:hidden mobile chrome (issue #39): the desktop Sidebar is `hidden
// md:flex`, so on phones there was no navigation at all. This is a top
// bar with a hamburger that opens the same NAV_ITEMS as a slide-in
// drawer. Rendered alongside <Sidebar/> in App so it covers every route.
export default function MobileNav() {
  const [open, setOpen] = useState(false)

  return (
    <div className="md:hidden">
      <header className="h-14 flex items-center justify-between px-3 border-b border-border-subtle bg-app">
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open navigation menu"
          className="w-9 h-9 flex items-center justify-center rounded-lg text-fg-muted hover:text-fg hover:bg-surface/60 transition-colors"
        >
          <i className="fa-solid fa-bars"></i>
        </button>
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center flex-shrink-0">
            <i className="fa-solid fa-cube text-white text-xs"></i>
          </div>
          <span className="font-bold truncate text-fg">LLM-Dock</span>
        </div>
        <ThemeSwitcher />
      </header>

      {open && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/60"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <nav
            className="fixed inset-y-0 left-0 z-50 w-64 bg-app border-r border-border flex flex-col"
            role="dialog"
            aria-label="Navigation"
          >
            <div className="h-14 flex items-center justify-between px-4 border-b border-border-subtle">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-7 h-7 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center flex-shrink-0">
                  <i className="fa-solid fa-cube text-white text-xs"></i>
                </div>
                <span className="font-bold truncate text-fg">LLM-Dock</span>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation menu"
                className="w-9 h-9 flex items-center justify-center rounded-lg text-fg-muted hover:text-fg hover:bg-surface/60 transition-colors"
              >
                <i className="fa-solid fa-xmark"></i>
              </button>
            </div>
            <div className="flex-1 py-2">
              {NAV_ITEMS.map(({ to, end, icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-3 ${
                      isActive
                        ? 'text-fg bg-surface-strong/70'
                        : 'text-fg-muted hover:bg-surface/50'
                    }`
                  }
                >
                  <i className={`fa-solid ${icon} w-5 text-center`}></i>
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>
          </nav>
        </>
      )}
    </div>
  )
}
