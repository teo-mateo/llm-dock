import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchAPI } from '../api'
import { startService, stopService, restartService } from '../services/lifecycle'
import useServicesSSE from '../hooks/useServicesSSE'
import RotateDefaultKeyModal from './RotateDefaultKeyModal'

function getEngine(name) {
  if (name === 'open-webui') return 'WebUI'
  if (name.startsWith('llamacpp-')) return 'llama.cpp'
  if (name.startsWith('vllm-')) return 'vLLM'
  if (name.startsWith('ds4-')) return 'DS4'
  return 'Unknown'
}

function isInfra(name) {
  return name === 'open-webui'
}

function FavoriteButton({ service, onToggleFavorite }) {
  if (isInfra(service.name)) return null
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onToggleFavorite(service.name) }}
      className="shrink-0 p-0.5 -ml-1 rounded hover:bg-surface-muted cursor-pointer transition-colors"
      title={service.favorite ? 'Remove from favorites' : 'Add to favorites'}
    >
      <i className={service.favorite ? 'fa-solid fa-star text-amber-400' : 'fa-regular fa-star text-fg-subtle hover:text-fg-muted'}></i>
    </button>
  )
}

function StatusDot({ status }) {
  const color = status === 'running'
    ? 'bg-success'
    : status === 'exited'
      ? 'bg-danger'
      : 'bg-fg-subtle'
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${color}`} />
}

function StatusLabel({ service }) {
  const s = service.status
  if (s === 'running') return <span className="text-success-fg">Running</span>
  if (s === 'exited') {
    const exitInfo = service.exit_code != null ? ` (exit ${service.exit_code})` : ''
    return <span className="text-danger-fg">Stopped{exitInfo}</span>
  }
  return <span className="text-fg-subtle">Not Created</span>
}

function EngineBadge({ engine }) {
  const colors = {
    'llama.cpp': 'bg-badge-llamacpp-bg text-badge-llamacpp-fg',
    'vLLM': 'bg-badge-vllm-bg text-badge-vllm-fg',
    'DS4': 'bg-badge-ds4-bg text-badge-ds4-fg',
    'WebUI': 'bg-badge-webui-bg text-badge-webui-fg',
    'Unknown': 'bg-badge-neutral-bg text-badge-neutral-fg'
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
      className="ml-2 text-fg-muted hover:text-fg text-lg leading-none cursor-pointer"
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
            className="p-1.5 text-lg leading-none rounded hover:bg-surface-muted text-fg-muted hover:text-fg cursor-pointer"
            title="Open"
          >
            ↗
          </a>
        )}
        <button
          onClick={e => { e.stopPropagation(); onRestart(service.name) }}
          disabled={!!isTransitioning}
          className="p-1.5 text-lg leading-none rounded hover:bg-surface-muted text-fg-muted hover:text-warning-fg disabled:opacity-50 cursor-pointer"
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
          className="p-1.5 text-lg leading-none rounded hover:bg-surface-muted text-fg-muted hover:text-danger-fg disabled:opacity-50 cursor-pointer"
          title="Stop"
        >
          {isTransitioning === 'stopping' ? '...' : '■'}
        </button>
      ) : (
        <button
          onClick={e => { e.stopPropagation(); onStart(service.name) }}
          disabled={!!isTransitioning}
          className="p-1.5 text-lg leading-none rounded hover:bg-surface-muted text-fg-muted hover:text-success-fg disabled:opacity-50 cursor-pointer"
          title="Start"
        >
          {isTransitioning === 'starting' ? '...' : '▶'}
        </button>
      )}
      <button
        onClick={e => { e.stopPropagation(); onEdit(service.name) }}
        className="p-1.5 text-lg leading-none rounded hover:bg-surface-muted text-fg-muted hover:text-accent-fg cursor-pointer"
        title="Edit"
      >
        ✎
      </button>
      <button
        onClick={e => { e.stopPropagation(); onViewLogs(service.name) }}
        className="p-1.5 text-lg leading-none rounded hover:bg-surface-muted text-fg-muted hover:text-purple-400 cursor-pointer"
        title="View logs"
      >
        <i className="fa-solid fa-terminal text-sm"></i>
      </button>
      <button
        onClick={e => { e.stopPropagation(); onDelete(service.name) }}
        disabled={!!isTransitioning}
        className="p-1.5 text-lg leading-none rounded hover:bg-surface-muted text-fg-muted hover:text-danger-fg disabled:opacity-50 cursor-pointer"
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
    <div className="fixed bottom-6 right-6 bg-danger text-white px-4 py-2 rounded shadow-lg text-sm z-50">
      {message}
    </div>
  )
}

export default function ServicesTable() {
  const navigate = useNavigate()
  const { services, error, connected, refresh, toggleFavorite } = useServicesSSE()
  const [transitioning, setTransitioning] = useState({})
  const [toast, setToast] = useState(null)
  const [search, setSearch] = useState('')
  const [showRotateKey, setShowRotateKey] = useState(false)

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
      refresh()
    } catch (err) {
      setToast(`Failed to set public port for ${name}: ${err.message}`)
    }
  }, [refresh])

  const handleToggleFavorite = useCallback(async (name) => {
    try {
      await toggleFavorite(name)
    } catch (err) {
      setToast(`Failed to toggle favorite for ${name}: ${err.message}`)
    }
  }, [toggleFavorite])

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
    return <p className="text-danger-fg mt-6">Services: {error}</p>
  }

  if (services === null) {
    return <p className="text-fg-subtle mt-6">Loading services...</p>
  }

  const term = search.trim().toLowerCase()
  const visible = term ? services.filter(s => s.name.toLowerCase().includes(term)) : services
  const favVisible = visible.filter(s => s.favorite)
  const otherVisible = visible.filter(s => !s.favorite)
  const showSeparator = favVisible.length > 0 && otherVisible.length > 0

  function ConnectionDot({ connected, error }) {
    let color
    let label

    if (error) {
      if (error.includes('reconnecting') && !error.includes('Authentication')) {
        color = 'bg-warning'
        label = 'Reconnecting...'
      } else {
        color = 'bg-danger'
        label = error
      }
    } else if (connected) {
      color = 'bg-success'
      label = 'Connected'
    } else {
      color = 'bg-fg-subtle'
      label = 'Disconnected'
    }

    return (
      <span
        className={`inline-block w-2 h-2 rounded-full ${color} cursor-help`}
        title={label}
      />
    )
  }

  return (
    <div className="mt-6">
      <div className="flex flex-col gap-3 mb-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-fg">Services</h2>
          <ConnectionDot connected={connected} error={error} />
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <div className="relative w-full sm:w-auto">
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter by name..."
              className="w-full sm:w-48 bg-surface border border-border rounded-lg px-3 py-1.5 text-sm text-fg placeholder-fg-subtle focus:outline-none focus:border-accent transition-colors"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-fg-subtle hover:text-fg-muted text-xs cursor-pointer"
              >
                ✕
              </button>
            )}
          </div>
          <button
            onClick={() => setShowRotateKey(true)}
            className="px-3 py-1.5 bg-surface-strong hover:bg-surface-muted text-fg text-sm rounded transition-colors flex items-center gap-1.5"
            title="Generate a new shared API key for all services"
          >
            <i className="fa-solid fa-key text-xs"></i>
            Rotate default key
          </button>
          <button
            onClick={() => navigate('/services/new')}
            className="px-3 py-1.5 bg-accent-strong hover:bg-accent text-white text-sm rounded transition-colors"
          >
            + New Service
          </button>
        </div>
      </div>
      {/* Mobile: stacked cards (no horizontal scroll) */}
      <div className="md:hidden space-y-2">
        {visible.length === 0 ? (
          <div className="rounded-lg border border-border px-4 py-8 text-center text-fg-muted">
            {services.length === 0
              ? 'No services configured'
              : `No services matching "${search}"`}
          </div>
        ) : (
          <>
            {favVisible.map(svc => (
              <ServiceCard
                key={svc.name}
                service={svc}
                transitioning={transitioning}
                onStart={handleStart}
                onStop={handleStop}
                onRestart={handleRestart}
                onSetPublicPort={handleSetPublicPort}
                onToggleFavorite={handleToggleFavorite}
                onEdit={handleEdit}
                onViewLogs={handleViewLogs}
                onDelete={handleDelete}
              />
            ))}
            {showSeparator && <div className="border-t border-border my-2" />}
            {otherVisible.map(svc => (
              <ServiceCard
                key={svc.name}
                service={svc}
                transitioning={transitioning}
                onStart={handleStart}
                onStop={handleStop}
                onRestart={handleRestart}
                onSetPublicPort={handleSetPublicPort}
                onToggleFavorite={handleToggleFavorite}
                onEdit={handleEdit}
                onViewLogs={handleViewLogs}
                onDelete={handleDelete}
              />
            ))}
          </>
        )}
      </div>

      {/* Desktop: table */}
      <div className="hidden md:block overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm text-left">
          <thead className="bg-surface text-fg-muted uppercase text-xs">
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
                  className="px-6 py-8 text-center text-fg-muted"
                >
                  {services.length === 0
                    ? 'No services configured'
                    : `No services matching "${search}"`}
                </td>
              </tr>
            ) : (
              <>
                {favVisible.map(svc => (
                  <ServiceRow
                    key={svc.name}
                    service={svc}
                    transitioning={transitioning}
                    onStart={handleStart}
                    onStop={handleStop}
                    onRestart={handleRestart}
                    onSetPublicPort={handleSetPublicPort}
                    onToggleFavorite={handleToggleFavorite}
                    onEdit={handleEdit}
                    onViewLogs={handleViewLogs}
                    onDelete={handleDelete}
                  />
                ))}
                {showSeparator && (
                  <tr>
                    <td colSpan={7} className="px-6 py-1.5 bg-surface-strong border-y border-border-subtle" />
                  </tr>
                )}
                {otherVisible.map(svc => (
                  <ServiceRow
                    key={svc.name}
                    service={svc}
                    transitioning={transitioning}
                    onStart={handleStart}
                    onStop={handleStop}
                    onRestart={handleRestart}
                    onSetPublicPort={handleSetPublicPort}
                    onToggleFavorite={handleToggleFavorite}
                    onEdit={handleEdit}
                    onViewLogs={handleViewLogs}
                    onDelete={handleDelete}
                  />
                ))}
              </>
            )}
          </tbody>
        </table>
      </div>
      {toast && <Toast message={toast} onDone={() => setToast(null)} />}
      {showRotateKey && (
        <RotateDefaultKeyModal
          onClose={() => setShowRotateKey(false)}
          onDone={refresh}
        />
      )}
    </div>
  )
}

function PortInline({ service, onSetPublicPort }) {
  const infra = isInfra(service.name)
  const port = service.host_port && service.host_port !== 9999 ? service.host_port : null
  const engine = getEngine(service.name)
  const isLlamaCpp = engine === 'llama.cpp'
  const isPublicPort = port === 3301

  if (!port) return <span className="font-mono text-fg-subtle">N/A</span>

  return (
      <div className="flex items-center gap-1.5">
        {isLlamaCpp ? (
          <a
            href={`http://${window.location.hostname}:${port}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            className="font-mono text-accent-fg hover:text-accent-fg-hover"
          >
            {port}
          </a>
        ) : (
          <span className="font-mono text-fg-muted">{port}</span>
        )}
        {!infra && (isPublicPort ? (
          <svg className="w-4 h-4 text-success-fg" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" title="Public port (3301)">
            <circle cx="12" cy="12" r="10" />
            <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
          </svg>
        ) : (
          <button
            onClick={e => { e.stopPropagation(); onSetPublicPort(service.name) }}
            className="text-fg-subtle hover:text-accent-fg text-lg leading-none cursor-pointer"
            title="Set to public port (3301)"
          >
            ◎
          </button>
        ))}
      </div>
  )
}

function PortCell({ service, onSetPublicPort }) {
  const port = service.host_port && service.host_port !== 9999 ? service.host_port : null
  return (
    <td className={`px-6 py-3${port ? '' : ' font-mono text-fg-subtle'}`}>
      <PortInline service={service} onSetPublicPort={onSetPublicPort} />
    </td>
  )
}

// Mobile (md:hidden) stacked card — same data/actions as a table row,
// no horizontal scroll (issue #39).
function ServiceCard({ service, transitioning, onStart, onStop, onRestart, onSetPublicPort, onToggleFavorite, onEdit, onViewLogs, onDelete }) {
  const engine = getEngine(service.name)
  const infra = isInfra(service.name)

  return (
    <div className={`rounded-lg border border-border p-3 ${service.status === 'running' ? 'bg-success-subtle' : 'bg-surface-muted'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex items-center font-medium text-fg">
          <FavoriteButton service={service} onToggleFavorite={onToggleFavorite} />
          {!infra ? (
            <button
              onClick={() => onEdit(service.name)}
              className="text-accent-fg hover:text-accent-fg-hover hover:underline cursor-pointer text-left break-all"
            >
              {service.name}
            </button>
          ) : (
            <span className="break-all">{service.name}</span>
          )}
          <CopyButton text={service.name} />
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <StatusDot status={service.status} />
          <StatusLabel service={service} />
        </div>
      </div>

      {service.api_key && (
        <p className="text-fg-muted font-mono text-xs mt-1 break-all">
          {service.api_key.slice(0, 12)}...
          <CopyButton text={service.api_key} />
        </p>
      )}

      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <div>
          <p className="text-fg-subtle text-[10px] uppercase tracking-wide mb-0.5">Port</p>
          <PortInline service={service} onSetPublicPort={onSetPublicPort} />
        </div>
        <div>
          <p className="text-fg-subtle text-[10px] uppercase tracking-wide mb-0.5">Engine</p>
          <EngineBadge engine={engine} />
        </div>
        <div>
          <p className="text-fg-subtle text-[10px] uppercase tracking-wide mb-0.5">Size</p>
          <span className="text-fg-muted text-xs">{service.model_size_str || '—'}</span>
        </div>
        <div>
          <p className="text-fg-subtle text-[10px] uppercase tracking-wide mb-0.5">Open WebUI</p>
          {infra ? (
            <span className="text-fg-faint">—</span>
          ) : service.openwebui_registered ? (
            <span className="text-success-fg text-xs">✓ Registered</span>
          ) : (
            <span className="text-fg-subtle text-xs">Not registered</span>
          )}
        </div>
      </div>

      <div className="mt-3 pt-2 border-t border-border-subtle flex justify-end">
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
      </div>
    </div>
  )
}

function ServiceRow({ service, transitioning, onStart, onStop, onRestart, onSetPublicPort, onToggleFavorite, onEdit, onViewLogs, onDelete }) {
  const engine = getEngine(service.name)
  const infra = isInfra(service.name)

  return (
    <tr className={`border-b border-border transition-colors ${service.status === 'running' ? 'bg-success-subtle hover:bg-success-subtle' : 'bg-surface-muted hover:bg-surface-strong'}`}>
      <td className="px-6 py-3 whitespace-nowrap">
        <div className="flex flex-col">
          <div className="flex items-center font-medium text-fg">
            <FavoriteButton service={service} onToggleFavorite={onToggleFavorite} />
            {!infra ? (
              <button
                onClick={() => onEdit(service.name)}
                className="text-accent-fg hover:text-accent-fg-hover hover:underline cursor-pointer text-left"
              >
                {service.name}
              </button>
            ) : (
              <span>{service.name}</span>
            )}
            <CopyButton text={service.name} />
          </div>
          {service.api_key && (
            <p className="text-fg-muted font-mono text-xs mt-1">
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
      <td className="px-6 py-3 text-fg-muted text-xs">
        {service.model_size_str || '—'}
      </td>
      <td className="px-6 py-3">
        {infra ? (
          <span className="text-fg-faint">—</span>
        ) : service.openwebui_registered ? (
          <span className="text-success-fg text-xs">✓ Registered</span>
        ) : (
          <span className="text-fg-subtle text-xs">Not registered</span>
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
