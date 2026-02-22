import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import GpuMonitor from './components/GpuMonitor'
import ServicesTable from './components/ServicesTable'
import ServiceDetailsPage from './components/ServiceDetailsPage'

function App() {
  return (
    <div className="flex h-screen bg-gray-900 text-gray-100">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <div className="flex-1 overflow-auto p-6 mx-auto w-full max-w-[1900px]">
          <Routes>
            <Route path="/" element={<><GpuMonitor /><ServicesTable /></>} />
            <Route path="/services/:serviceName/*" element={<ServiceDetailsPage />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

export default App
