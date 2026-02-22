import { NavLink } from 'react-router-dom'

function Sidebar() {
  return (
    <aside className="hidden md:flex w-56 bg-gray-900 border-r border-gray-800 flex-col flex-shrink-0">
      {/* Logo */}
      <div className="h-16 px-4 border-b border-gray-800 flex items-center">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
            <i className="fa-solid fa-cube text-white text-sm"></i>
          </div>
          <div>
            <h1 className="font-bold text-lg">LLM-Dock</h1>
            <p className="text-xs text-gray-500">v1.0.0</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            `flex items-center gap-3 px-4 py-2.5 ${
              isActive
                ? 'text-white bg-gray-800/70'
                : 'text-gray-400 hover:bg-gray-800/50'
            }`
          }
        >
          <i className="fa-solid fa-server w-5 text-center"></i>
          <span>Services</span>
        </NavLink>
      </nav>

      {/* User section */}
      <div className="p-4 border-t border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-gray-700 rounded-full flex items-center justify-center">
            <i className="fa-solid fa-user text-gray-400 text-sm"></i>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">Admin</p>
          </div>
          <button className="text-gray-500 hover:text-gray-300">
            <i className="fa-solid fa-right-from-bracket"></i>
          </button>
        </div>
      </div>
    </aside>
  )
}

export default Sidebar
