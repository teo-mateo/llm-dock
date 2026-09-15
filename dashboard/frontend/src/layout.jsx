import { Outlet } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import MobileNav from './components/MobileNav'
import Header from './components/Header'

function DefaultLayout({ children }) {
  return (
    <>
      <Header />
      <div className="flex-1 overflow-auto p-3 md:p-6 mx-auto w-full max-w-[1900px]">
        {children}
      </div>
    </>
  )
}

// App shell as a data-router layout element: it stays mounted across route
// changes (exactly the legacy BrowserRouter-App-<Routes> shape, where the
// shell wrapped <Routes> and only the matched route swapped), and the
// matched child renders through the Outlet.
function AppShell() {
  return (
    <div className="flex h-screen bg-app text-fg">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden min-w-0">
        <MobileNav />
        <Outlet />
      </main>
    </div>
  )
}

export { DefaultLayout, AppShell }
