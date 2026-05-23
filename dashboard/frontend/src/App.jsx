import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import MobileNav from './components/MobileNav'
import Header from './components/Header'
import GpuMonitor from './components/GpuMonitor'
import ServicesTable from './components/ServicesTable'
import ServiceDetailsPage from './components/ServiceDetailsPage'
import ChatPage from './components/chat/ChatPage'
import ToolsPage from './components/tools/ToolsPage'

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

function App() {
  return (
    <div className="flex h-screen bg-app text-fg">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden min-w-0">
        <MobileNav />
        <Routes>
          {/* Single route with an optional :conversationId so the empty
              /chat URL and /chat/<id> both render the SAME ChatPage
              instance. With two separate <Route> entries React Router
              unmounts/remounts on the transition, which drops the
              pendingMsgRef holding the empty-state composer's first
              message. */}
          <Route path="/chat/:conversationId?" element={<ChatPage />} />
          <Route path="/tools" element={<DefaultLayout><ToolsPage /></DefaultLayout>} />
          <Route path="/" element={<DefaultLayout><GpuMonitor /><ServicesTable /></DefaultLayout>} />
          <Route path="/services/:serviceName/*" element={<DefaultLayout><ServiceDetailsPage /></DefaultLayout>} />
        </Routes>
      </main>
    </div>
  )
}

export default App
