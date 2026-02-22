import Sidebar from './components/Sidebar'
import Header from './components/Header'
import GpuMonitor from './components/GpuMonitor'
import ServicesTable from './components/ServicesTable'

function App() {
  return (
    <div className="flex h-screen bg-gray-900 text-gray-100">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <div className="flex-1 overflow-auto p-6">
          <GpuMonitor />
          <ServicesTable />
        </div>
      </main>
    </div>
  )
}

export default App
