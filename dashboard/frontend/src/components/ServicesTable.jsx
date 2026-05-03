import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchAPI } from '../api'
import { startService, stopService, restartService } from '../services/lifecycle'
import useServicesSSE from '../hooks/useServicesSSE'

function getEngine(name) {
  if (name === 'open-webui') return 'WebUI'
  if (name.startsWith('llamacpp-')) return 'llama.cpp'
  if (name.startsWith('vllm-')) return 'vLLM'
  return 'Unknown'
}

function isInfra(name) {
  return name === 'open-webui'
}

function StatusDot({ status }) {
  const color = status === 'running'
    ? 'bg-green-400'
    : status === 'exited'
      ? 'bg-red-400'
      : 'bg-gray-500'
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${color}`} />
}

function StatusLabel({ service }) {
  const s = service.status
  if (s === 'running') return <span className="text-green-400">Running</span>
  if (s === 'exited') {
    const exitInfo = service.exit_code != null ? ` (exit ${service.exit_code})` : ''
    return <span className="text-red-400">Stopped{exitInfo}</span>
  }
  return <span className="text-gray-500">Not Created</span>
}

function EngineBadge({ engine }) {
  const colors = {
    'llama.cpp': 'bg-blue-600/30 text-blue-300',
    'vLLM': 'bg-purple-600/30 text-purple-300',
    'WebUI': 'bg-emerald-600/30 text-emerald-300',
    'Unknown': 'bg-gray-600/30 text-gray-400'
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[engine] || colors.Unknown}`}>
      {engine}
    </span>
  )
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = (e) => {
    e.stopPropagation()
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button
      onClick={handleCopy}
      className="ml-2 text-gray-400 hover:text-gray-200 text-lg leading-none cursor-pointer"
      title="Copy"
    >
      {copied ? '✓' : '⧉'}
    </button>
  )
}



function ActionButtons({ service, transitioning, onStart, onStop, onRestart, onDelete, onEdit, onViewLogs }) {
  const infra = isInfra(service.name)
  const isTransitioning = transitioning[service.name]

  if (infra) {
    return (
      <div className="flex gap-1">
        {service.status === 'running' && service.host_port && (
          <a
            href={`http://${window.location.hostname}:${service.host_port}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            className="p-1.5 text-lg leading-none rounded hover:bg-gray-600 text-gray-400 hover:text-gray-200 cursor-pointer"
            title="Open"
          >
            ↗
          </a>
        )}
        <button
          onClick={e => { e.stopPropagation(); onRestart(service.name) }}
          disabled={!!isTransitioning}
          className="p-1.5 text-lg leading-none rounded hover:bg-gray-600 text-gray-400 hover:text-yellow-300 disabled:opacity-50 cursor-pointer"
          title="Restart"
        >
          ↻
        </button>
      </div>
    )
  }

  return (
    <div className="flex gap-1">
      {service.status === 'running' ? (
        <button
          onClick={e => { e.stopPropagation(); onStop(service.name) }}
          disabled={!!isTransitioning}
          className="p-1.5 text-lg leading-none rounded hover:bg-gray-600 text-gray-400 hover:text-red-400 disabled:opacity-50 cursor-pointer"
          title="Stop"
        >
          {isTransitioning === 'stopping' ? '...' : '■'}
        </button>
      ) : (
        <button
          onClick={e => { e.stopPropagation(); onStart(service.name) }}
          disabled={!!isTransitioning}
          className="p-1.5 text-lg leading-none rounded hover:bg-gray-600 text-gray-400 hover:text-green-400 disabled:opacity-50 cursor-pointer"
          title="Start"
        >
          {isTransitioning === 'starting' ? '...' : '▶'}
        </button>
      )}
      <button
        onClick={e => { e.stopPropagation(); onEdit(service.name) }}
        className="p-1.5 text-lg leading-none rounded hover:bg-gray-600 text-gray-400 hover:text-blue-400 cursor-pointer"
        title="Edit"
      >
        ✎
      </button>
      <button
        onClick={e => { e.stopPropagation(); onViewLogs(service.name) }}
        className="p-1.5 text-lg leading-none rounded hover:bg-gray-600 text-gray-400 hover:text-purple-400 cursor-pointer"
        title="View logs"
      >
        <i className="fa-solid fa-terminal text-sm"></i>
      </button>
      <button
        onClick={e => { e.stopPropagation(); onDelete(service.name) }}
        disabled={!!isTransitioning}
        className="p-1.5 text-lg leading-none rounded hover:bg-gray-600 text-gray-400 hover:text-red-400 disabled:opacity-50 cursor-pointer"
        title="Delete"
      >
        ✕
      </button>
    </div>
  )
}

function Toast({ message, onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3000)
    return () => clearTimeout(t)
  }, [onDone])

  return (
    <div className="fixed bottom-6 right-6 bg-red-600 text-white px-4 py-2 rounded shadow-lg text-sm z-50">
      {message}
    </div>
  )
}

export default function ServicesTable() {
  const navigate = useNavigate()
  const { services, error } = useServicesSSE()
  const [transitioning, setTransitioning] = useState({})
  const [toast, setToast] = useState(null)
  const [search, setSearch] = useState('')

  const withTransition = useCallback(async (name, action, apiCall) => {
    setTransitioning(prev => ({ ...prev, [name]: action }))
    try {
      await apiCall()
    } catch (err) {
      setToast(`Failed to ${action} ${name}: ${err.message}`)
    } finally {
      setTransitioning(prev => { const n = { ...prev }; delete n[name]; return n })
    }
  }, [])

  const handleStart = useCallback((name) => {
    withTransition(name, 'starting', () => startService(name))
  }, [withTransition])

  const handleRestart = useCallback((name) => {
    withTransition(name, 'restarting', () => restartService(name))
  }, [withTransition])

  const handleStop = useCallback((name) => {
    withTransition(name, 'stopping', () => stopService(name))
  }, [withTransition])

  const handleSetPublicPort = useCallback(async (name) => {
    try {
      await fetchAPI(`/services/${name}/set-public-port`, { method: 'POST' })
    } catch (err) {
      setToast(`Failed to set public port for ${name}: ${err.message}`)
    }
  }, [])

  const handleEdit = (name) => {
    navigate(`/services/${name}`)
  }

  const handleViewLogs = (name) => {
    navigate(`/services/${name}/logs`)
  }

  const handleDelete = useCallback(async (name) => {
    if (!window.confirm(`Delete service "${name}"? This cannot be undone.`)) return
    setTransitioning(prev => ({ ...prev, [name]: 'deleting' }))
    try {
      await fetchAPI(`/services/${name}`, { method: 'DELETE' })
    } catch (err) {
      setToast(`Failed to delete ${name}: ${err.message}`)
    } finally {
      setTransitioning(prev => { const n = { ...prev }; delete n[name]; return n })
    }
  }, [])

  if (error) {
    return <p className="text-red-400 mt-6">Services: {error}</p>
  }

  if (services === null) {
    return <p className="text-gray-500 mt-6">Loading services...</p>
  }

  const term = search.trim().toLowerCase()
  const visible = term ? services.filter(s => s.name.toLowerCase().includes(term)) : services

  return (
    <div className="mt-6">
      <div className="flex items-center justify-between mb-3 gap-3">
        <h2 className="text-lg font-semibold text-gray-200">Services</h2>
        <div className="flex items-center gap-3">
          <div className="relative">
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter by name..."
              className="w-48 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs cursor-pointer"
              >
                ✕
              </button>
            )}
          </div>
          <button
            onClick={() => navigate('/services/new')}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition-colors"
          >
            + New Service
          </button>
        </div>
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-700">
        <table className="w-full text-sm text-left">
          <thead className="bg-gray-800 text-gray-400 uppercase text-xs">
            <tr>
              <th className="px-6 py-3">Service</th>
              <th className="px-6 py-3">Status</th>
              <th className="px-6 py-3">Port</th>
              <th className="px-6 py-3">Engine</th>
              <th className="px-6 py-3">Size</th>
              <th className="px-6 py-3">Open WebUI</th>
              <th className="px-6 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-6 py-8 text-center text-gray-400"
                >
                  {services.length === 0
                    ? 'No services configured'
                    : `No services matching "${search}"`}
                </td>
              </tr>
            ) : (
              visible.map(svc => (
                <ServiceRow
                  key={svc.name}
                  service={svc}
                  transitioning={transitioning}
                  onStart={handleStart}
                  onStop={handleStop}
                  onRestart={handleRestart}
                  onSetPublicPort={handleSetPublicPort}
                  onEdit={handleEdit}
                  onViewLogs={handleViewLogs}
                  onDelete={handleDelete}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
      {toast && <Toast message={toast} onDone={() => setToast(null)} />}
    </div>
  )
}

function PortCell({ service, onSetPublicPort }) {
  const infra = isInfra(service.name)
  const port = service.host_port && service.host_port !== 9999 ? service.host_port : null
  const engine = getEngine(service.name)
  const isLlamaCpp = engine === 'llama.cpp'
  const isPublicPort = port === 3301

  if (!port) return <td className="px-6 py-3 font-mono text-gray-500">N/A</td>

  return (
    <td className="px-6 py-3">
      <div className="flex items-center gap-1.5">
        {isLlamaCpp ? (
          <a
            href={`http://${window.location.hostname}:${port}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            className="font-mono text-blue-400 hover:text-blue-300"
          >
            {port}
          </a>
        ) : (
          <span className="font-mono text-gray-300">{port}</span>
        )}
        {!infra && (isPublicPort ? (
          <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" title="Public port (3301)">
            <circle cx="12" cy="12" r="10" />
            <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
          </svg>
        ) : (
          <button
            onClick={e => { e.stopPropagation(); onSetPublicPort(service.name) }}
            className="text-gray-500 hover:text-blue-400 text-lg leading-none cursor-pointer"
            title="Set to public port (3301)"
          >
            ◎
          </button>
        ))}
      </div>
    </td>
  )
}

function ServiceRow({ service, transitioning, onStart, onStop, onRestart, onSetPublicPort, onEdit, onViewLogs, onDelete }) {
  const engine = getEngine(service.name)
  const infra = isInfra(service.name)

  return (
    <tr className="border-b border-gray-700 bg-gray-800/50 hover:bg-gray-700/50 transition-colors">
      <td className="px-6 py-3">
        <div className="flex flex-col">
          <div className="flex items-center font-medium text-gray-200">
            {!infra ? (
              <button
                onClick={() => onEdit(service.name)}
                className="text-blue-400 hover:text-blue-300 hover:underline cursor-pointer text-left"
              >
                {service.name}
              </button>
            ) : (
              <span>{service.name}</span>
            )}
            <CopyButton text={service.name} />
          </div>
          {service.api_key && (
            <p className="text-gray-400 font-mono text-xs mt-1">
              {service.api_key.slice(0, 12)}...
              <CopyButton text={service.api_key} />
            </p>
          )}
        </div>
      </td>
      <td className="px-6 py-3">
        <div className="flex items-center gap-2">
          <StatusDot status={service.status} />
          <StatusLabel service={service} />
        </div>
      </td>
      <PortCell service={service} onSetPublicPort={onSetPublicPort} />
      <td className="px-6 py-3"><EngineBadge engine={engine} /></td>
      <td className="px-6 py-3 text-gray-300 text-xs">
        {service.model_size_str || '—'}
      </td>
      <td className="px-6 py-3">
        {infra ? (
          <span className="text-gray-600">—</span>
        ) : service.openwebui_registered ? (
          <span className="text-green-400 text-xs">✓ Registered</span>
        ) : (
          <span className="text-gray-500 text-xs">Not registered</span>
        )}
      </td>
      <td className="px-6 py-3">
        <ActionButtons
          service={service}
          transitioning={transitioning}
          onStart={onStart}
          onStop={onStop}
          onRestart={onRestart}
          onEdit={onEdit}
          onViewLogs={onViewLogs}
          onDelete={onDelete}
        />
      </td>
    </tr>
  )
}
