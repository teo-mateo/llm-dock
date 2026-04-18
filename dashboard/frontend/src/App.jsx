import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import GpuMonitor from './components/GpuMonitor'
import ServicesTable from './components/ServicesTable'
import ServiceDetailsPage from './components/ServiceDetailsPage'
import ChatPage from './components/chat/ChatPage'

function DefaultLayout({ children }) {
  return (
    <>
      <Header />
      <div className="flex-1 overflow-auto p-6 mx-auto w-full max-w-[1900px]">
        {children}
      </div>
    </>
  )
}

function App() {
  return (
    <div className="flex h-screen bg-gray-900 text-gray-100">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">
        <Routes>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:conversationId" element={<ChatPage />} />
          <Route path="/" element={<DefaultLayout><GpuMonitor /><ServicesTable /></DefaultLayout>} />
          <Route path="/services/:serviceName/*" element={<DefaultLayout><ServiceDetailsPage /></DefaultLayout>} />
        </Routes>
      </main>
    </div>
  )
}

export default App
