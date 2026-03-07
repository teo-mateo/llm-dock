import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom'
import useServiceDetails from '../hooks/useServiceDetails'
import { fetchAPI } from '../api'
import ServiceDetailsHeader from './ServiceDetailsHeader'
import ServiceConfigPanel from './ServiceConfigPanel'
import ServiceLogsPanel from './ServiceLogsPanel'
import ParameterReference from './ParameterReference'
import BenchmarkTab from './BenchmarkTab'

function Toast({ message, type, onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3000)
    return () => clearTimeout(t)
  }, [onDone])

  const bgColor = type === 'success' ? 'bg-green-600' : 'bg-red-600'

  return (
    <div className={`fixed bottom-6 right-6 ${bgColor} text-white px-4 py-2 rounded shadow-lg text-sm z-50`} role="alert">
      {message}
    </div>
  )
}

function TabBar({ serviceName, activeTab, isLlamaCpp }) {
  const tabs = [
    { id: 'config', label: 'Configuration', path: `/services/${serviceName}` },
    { id: 'logs', label: 'Logs', path: `/services/${serviceName}/logs` },
  ]
  if (isLlamaCpp) {
    tabs.push({ id: 'benchmark', label: 'Benchmark', path: `/services/${serviceName}/benchmark` })
  }

  return (
    <div className="flex gap-6 border-b border-gray-700 mb-6">
      {tabs.map(tab => (
        <Link
          key={tab.id}
          to={tab.path}
          className={`pb-3 text-sm font-medium cursor-pointer ${
            activeTab === tab.id
              ? 'border-b-2 border-blue-500 text-white'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  )
}

const SKELETON_WIDTHS = [68, 85, 73, 91, 78, 64, 82, 96]

function LoadingSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="bg-gray-800 border-b border-gray-700 px-6 py-4 -mx-6 -mt-6 mb-6">
        <div className="flex items-center gap-4">
          <div className="h-5 w-32 bg-gray-700/50 rounded" />
          <div className="w-px h-6 bg-gray-700" />
          <div className="h-7 w-48 bg-gray-700/50 rounded" />
          <div className="h-6 w-20 bg-gray-700/50 rounded-full" />
          <div className="h-5 w-16 bg-gray-700/50 rounded" />
        </div>
      </div>
      {/* Tab bar skeleton */}
      <div className="flex gap-6 border-b border-gray-700 mb-6">
        <div className="h-4 w-24 bg-gray-700/50 rounded mb-3" />
        <div className="h-4 w-12 bg-gray-700/50 rounded mb-3" />
      </div>
      {/* Config + Reference skeleton */}
      <div className="grid grid-cols-1 xl:grid-cols-[60%_1fr] gap-6">
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-5">
          <div className="h-4 w-24 bg-gray-700/50 rounded mb-4" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i}>
                <div className="h-3 w-16 bg-gray-700/50 rounded mb-2" />
                <div className="h-5 w-32 bg-gray-700/50 rounded" />
              </div>
            ))}
          </div>
        </div>
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-5">
          <div className="h-4 w-32 bg-gray-700/50 rounded mb-4" />
          <div className="space-y-2">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="h-4 bg-gray-700/50 rounded" style={{ width: `${SKELETON_WIDTHS[i]}%` }} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function NotFoundError({ serviceName }) {
  const navigate = useNavigate()
  return (
    <div className="flex flex-col items-center justify-center py-20">
      <i className="fa-solid fa-circle-exclamation text-4xl text-gray-500 mb-4"></i>
      <h2 className="text-xl font-semibold text-white mb-2">Service not found</h2>
      <p className="text-gray-400 mb-6">
        The service "{serviceName}" does not exist or has been deleted.
      </p>
      <button
        onClick={() => navigate('/')}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium cursor-pointer"
      >
        Back to Services
      </button>
    </div>
  )
}

export default function ServiceDetailsPage() {
  const { serviceName } = useParams()
  const location = useLocation()
  const {
    config, runtime, loading, error, transitioning,
    refetchConfig, actions,
  } = useServiceDetails(serviceName)
  const [toast, setToast] = useState(null)
  const [flagMetadata, setFlagMetadata] = useState(null)
  const [existingFlags, setExistingFlags] = useState([])
  const addFlagRef = useRef(null)
  const metadataFetchId = useRef(0)

  const activeTab = location.pathname.endsWith('/benchmark') ? 'benchmark'
    : location.pathname.endsWith('/logs') ? 'logs'
    : 'config'
  const templateType = config?.template_type
  const isLlamaCpp = templateType === 'llamacpp'

  // Fetch flag metadata at page level for both ConfigPanel and ParameterReference
  useEffect(() => {
    if (!templateType) return
    const id = ++metadataFetchId.current
    fetchAPI(`/flag-metadata/${templateType}`)
      .then(data => { if (metadataFetchId.current === id) setFlagMetadata(data.optional_flags || {}) })
      .catch(() => {})
  }, [templateType])

  const handleError = useCallback((message) => {
    setToast({ message, type: 'error' })
  }, [])

  const handleSuccess = useCallback((message) => {
    setToast({ message, type: 'success' })
  }, [])

  const handleSaved = useCallback((message) => {
    setToast({ message, type: 'success' })
    refetchConfig()
  }, [refetchConfig])

  const handleParamsChange = useCallback((flags) => {
    setExistingFlags(flags)
  }, [])

  const handleAddFlag = useCallback((flag, defaultValue) => {
    if (addFlagRef.current) addFlagRef.current(flag, defaultValue)
  }, [])

  if (loading) return <LoadingSkeleton />
  if (error === 'not-found') return <NotFoundError serviceName={serviceName} />
  if (error) {
    return (
      <div className="text-red-400 py-10 text-center">
        <i className="fa-solid fa-triangle-exclamation mr-2"></i>
        Failed to load service: {error}
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      <ServiceDetailsHeader
        serviceName={serviceName}
        config={config}
        runtime={runtime}
        transitioning={transitioning}
        actions={actions}
        onRename={actions.rename}
        onSuccess={handleSuccess}
        onError={handleError}
      />

      <TabBar serviceName={serviceName} activeTab={activeTab} isLlamaCpp={isLlamaCpp} />

      {activeTab === 'logs' ? (
        <div className="flex-1 min-h-0">
          <ServiceLogsPanel serviceName={serviceName} runtime={runtime} />
        </div>
      ) : activeTab === 'benchmark' ? (
        <BenchmarkTab
          serviceName={serviceName}
          config={config}
          onSuccess={handleSuccess}
          onError={handleError}
        />
      ) : (
        <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-[60%_1fr] gap-6 content-start">
          <div>
            <ServiceConfigPanel
              config={config}
              serviceName={serviceName}
              runtime={runtime}
              onSaved={handleSaved}
              onError={handleError}
              flagMetadata={flagMetadata}
              onParamsChange={handleParamsChange}
              addFlagRef={addFlagRef}
            />
          </div>
          <div className="relative min-h-0 overflow-hidden">
            <div className="absolute inset-0 overflow-hidden">
              <ParameterReference
                flagMetadata={flagMetadata}
                existingFlags={existingFlags}
                onAddFlag={handleAddFlag}
              />
            </div>
          </div>
        </div>
      )}

      {toast && <Toast message={toast.message} type={toast.type} onDone={() => setToast(null)} />}
    </div>
  )
}
