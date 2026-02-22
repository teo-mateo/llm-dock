import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

function CopyButton({ text, label }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button
      onClick={handleCopy}
      className="text-gray-400 hover:text-gray-200 cursor-pointer"
      aria-label={label}
      title={label}
    >
      <i className={`fa-solid ${copied ? 'fa-check text-green-400' : 'fa-copy'} text-sm`}></i>
    </button>
  )
}

function StatusBadge({ status, transitioning }) {
  let bgClass, textClass, borderClass, label

  if (transitioning) {
    bgClass = 'bg-yellow-500/20'
    textClass = 'text-yellow-400'
    borderClass = 'border-yellow-500/30'
    label = transitioning === 'starting' ? 'Starting...' : transitioning === 'stopping' ? 'Stopping...' : 'Restarting...'
  } else if (status === 'running') {
    bgClass = 'bg-green-500/20'
    textClass = 'text-green-400'
    borderClass = 'border-green-500/30'
    label = 'Running'
  } else if (status === 'exited') {
    bgClass = 'bg-red-500/20'
    textClass = 'text-red-400'
    borderClass = 'border-red-500/30'
    label = 'Stopped'
  } else {
    bgClass = 'bg-gray-500/20'
    textClass = 'text-gray-400'
    borderClass = 'border-gray-500/30'
    label = 'Not Created'
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${bgClass} ${textClass} ${borderClass}`}
      role="status"
      aria-live="polite"
      aria-label={`Service status: ${label}`}
    >
      <span className={`w-2 h-2 rounded-full ${transitioning ? 'animate-pulse' : ''} ${
        transitioning ? 'bg-yellow-400' : status === 'running' ? 'bg-green-400' : status === 'exited' ? 'bg-red-400' : 'bg-gray-400'
      }`} />
      {label}
    </span>
  )
}

function EngineBadge({ templateType }) {
  const engineMap = {
    llamacpp: { label: 'llama.cpp', classes: 'bg-blue-600/30 text-blue-300' },
    vllm: { label: 'vLLM', classes: 'bg-purple-600/30 text-purple-300' },
  }
  const engine = engineMap[templateType] || { label: templateType, classes: 'bg-gray-600/30 text-gray-400' }

  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${engine.classes}`}>
      {engine.label}
    </span>
  )
}

function InlineRename({ serviceName, onRename, onCancel }) {
  const [newName, setNewName] = useState(serviceName)
  const [renaming, setRenaming] = useState(false)

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault()
    const trimmed = newName.trim()
    if (!trimmed || trimmed === serviceName) {
      onCancel()
      return
    }
    setRenaming(true)
    try {
      await onRename(trimmed)
    } catch {
      setRenaming(false)
    }
  }, [newName, serviceName, onRename, onCancel])

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <input
        autoFocus
        value={newName}
        onChange={e => setNewName(e.target.value)}
        disabled={renaming}
        className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xl font-bold text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
        onKeyDown={e => e.key === 'Escape' && onCancel()}
      />
      <button
        type="submit"
        disabled={renaming}
        className="text-green-400 hover:text-green-300 disabled:opacity-50 cursor-pointer"
        title="Confirm rename"
      >
        <i className={`fa-solid ${renaming ? 'fa-spinner fa-spin' : 'fa-check'}`}></i>
      </button>
      <button
        type="button"
        onClick={onCancel}
        disabled={renaming}
        className="text-gray-400 hover:text-gray-200 disabled:opacity-50 cursor-pointer"
        title="Cancel rename"
      >
        <i className="fa-solid fa-xmark"></i>
      </button>
    </form>
  )
}

function YamlPreviewModal({ yaml, onClose }) {
  useEffect(() => {
    const handler = e => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-gray-800 rounded-lg border border-gray-700 max-w-3xl w-full max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-gray-700 flex justify-between items-center">
          <h3 className="text-lg font-semibold text-gray-200">Docker Compose YAML</h3>
          <div className="flex items-center gap-3">
            <CopyButton text={yaml} label="Copy YAML" />
            <button onClick={onClose} className="text-gray-400 hover:text-gray-200 cursor-pointer" aria-label="Close">
              <i className="fa-solid fa-xmark"></i>
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-auto p-5">
          <pre className="font-mono text-sm text-gray-300 whitespace-pre-wrap">{yaml}</pre>
        </div>
      </div>
    </div>
  )
}

function MetadataRow({ config, runtime }) {
  const status = runtime?.status || 'not-created'
  const isRunning = status === 'running'
  const port = runtime?.host_port && runtime.host_port !== 9999 ? runtime.host_port : config?.port
  const isPublicPort = port === 3301
  const apiKey = runtime?.api_key || config?.api_key
  const containerId = runtime?.container_id

  const isRegistered = runtime?.openwebui_registered

  return (
    <div className="flex items-center gap-4 flex-wrap pt-3 mt-3 border-t border-gray-700">
      {/* Port */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-gray-400">Port:</span>
        {port ? (
          <>
            {isRunning ? (
              <a
                href={`http://${window.location.hostname}:${port}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-mono text-blue-400 hover:text-blue-300"
              >
                {port}
              </a>
            ) : (
              <span className="text-xs font-mono text-white">{port}</span>
            )}
            {isPublicPort && (
              <span className="text-green-400" title="Public port (3301)">
                <i className="fa-solid fa-globe text-xs"></i>
              </span>
            )}
          </>
        ) : (
          <span className="text-xs text-gray-500">N/A</span>
        )}
      </div>

      {/* API Key */}
      {apiKey && (
        <>
          <div className="w-px h-4 bg-gray-700" />
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-400">API Key:</span>
            <span className="text-xs font-mono text-white">{apiKey.slice(0, 16)}...</span>
            <CopyButton text={apiKey} label="Copy API key" />
          </div>
        </>
      )}

      {/* Container ID */}
      {containerId && (
        <>
          <div className="w-px h-4 bg-gray-700" />
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-400">Container:</span>
            <span className="text-xs font-mono text-white">{containerId.slice(0, 7)}</span>
            <CopyButton text={containerId} label="Copy container ID" />
          </div>
        </>
      )}

      {/* Open WebUI status */}
      <>
        <div className="w-px h-4 bg-gray-700" />
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-400">WebUI:</span>
          {isRegistered ? (
            <span className="text-xs text-green-400">Registered</span>
          ) : (
            <span className="text-xs text-gray-500">Not registered</span>
          )}
        </div>
      </>

      {/* Exit code */}
      {status === 'exited' && runtime?.exit_code != null && (
        <>
          <div className="w-px h-4 bg-gray-700" />
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-400">Exit code:</span>
            <span className="text-xs text-white">{runtime.exit_code}</span>
          </div>
        </>
      )}
    </div>
  )
}

function ToolbarRow({ config, runtime, transitioning, actions, onSuccess, onError }) {
  const [yamlPreview, setYamlPreview] = useState(null)
  const [settingPublicPort, setSettingPublicPort] = useState(false)
  const [togglingWebUI, setTogglingWebUI] = useState(false)

  const status = runtime?.status || 'not-created'
  const isRunning = status === 'running'
  const disabled = !!transitioning
  const port = config?.port
  const isPublicPort = port === 3301
  const isRegistered = runtime?.openwebui_registered

  const handleLifecycleAction = async (actionFn) => {
    try {
      await actionFn()
    } catch (err) {
      onError(err.message)
    }
  }

  const handleViewYaml = useCallback(async () => {
    try {
      const yaml = await actions.fetchYamlPreview()
      setYamlPreview(yaml)
    } catch (err) {
      onError(`Failed to load YAML: ${err.message}`)
    }
  }, [actions, onError])

  const handleSetPublicPort = useCallback(async () => {
    setSettingPublicPort(true)
    try {
      const data = await actions.setPublicPort()
      const displaced = data.updates?.find(u => u.service !== config?.service_name && u.old_port === 3301)
      if (displaced) {
        onSuccess(`Now on port 3301. ${displaced.service} moved to port ${displaced.new_port}.`)
      } else {
        onSuccess('Now on port 3301.')
      }
    } catch (err) {
      onError(`Failed to set public port: ${err.message}`)
    } finally {
      setSettingPublicPort(false)
    }
  }, [actions, config, onSuccess, onError])

  const handleToggleWebUI = useCallback(async () => {
    setTogglingWebUI(true)
    try {
      if (isRegistered) {
        await actions.unregisterOpenWebUI()
        onSuccess('Unregistered from Open WebUI.')
      } else {
        await actions.registerOpenWebUI()
        onSuccess('Registered with Open WebUI.')
      }
    } catch (err) {
      onError(`Open WebUI ${isRegistered ? 'unregister' : 'register'} failed: ${err.message}`)
    } finally {
      setTogglingWebUI(false)
    }
  }, [isRegistered, actions, onSuccess, onError])

  const toolbarBtnBase = 'px-3 py-1.5 rounded text-xs font-medium inline-flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer'

  return (
    <>
      <div className="flex items-center gap-2 flex-wrap mt-3 pt-3 border-t border-gray-700">
        {/* Group 1: Lifecycle */}
        {isRunning ? (
          <>
            <button
              onClick={() => handleLifecycleAction(actions.stop)}
              disabled={disabled}
              className={`${toolbarBtnBase} bg-red-600 hover:bg-red-700 text-white`}
            >
              {transitioning === 'stopping' ? (
                <i className="fa-solid fa-spinner fa-spin"></i>
              ) : (
                <i className="fa-solid fa-stop"></i>
              )}
              {transitioning === 'stopping' ? 'Stopping...' : 'Stop'}
            </button>
            <button
              onClick={() => handleLifecycleAction(actions.restart)}
              disabled={disabled}
              className={`${toolbarBtnBase} bg-yellow-600 hover:bg-yellow-700 text-white`}
            >
              {transitioning === 'restarting' ? (
                <i className="fa-solid fa-spinner fa-spin"></i>
              ) : (
                <i className="fa-solid fa-rotate-right"></i>
              )}
              {transitioning === 'restarting' ? 'Restarting...' : 'Restart'}
            </button>
          </>
        ) : (
          <button
            onClick={() => handleLifecycleAction(actions.start)}
            disabled={disabled}
            className={`${toolbarBtnBase} bg-green-600 hover:bg-green-700 text-white`}
          >
            {transitioning === 'starting' ? (
              <i className="fa-solid fa-spinner fa-spin"></i>
            ) : (
              <i className="fa-solid fa-play"></i>
            )}
            {transitioning === 'starting' ? 'Starting...' : 'Start'}
          </button>
        )}

        {/* Divider between groups */}
        <div className="w-px h-5 bg-gray-600 mx-1" />

        {/* Group 2: Actions */}
        {!isPublicPort ? (
          <button
            onClick={handleSetPublicPort}
            disabled={settingPublicPort}
            className={`${toolbarBtnBase} bg-gray-600 hover:bg-gray-700 text-white`}
          >
            {settingPublicPort ? (
              <i className="fa-solid fa-spinner fa-spin"></i>
            ) : (
              <i className="fa-solid fa-globe"></i>
            )}
            {settingPublicPort ? 'Setting...' : 'Set as Public'}
          </button>
        ) : (
          <span className="px-3 py-1.5 rounded text-xs font-medium inline-flex items-center gap-1.5 bg-green-600/20 text-green-400 border border-green-600/30">
            <i className="fa-solid fa-globe"></i>
            Public (3301)
          </span>
        )}

        <button
          onClick={handleViewYaml}
          className={`${toolbarBtnBase} bg-gray-600 hover:bg-gray-700 text-white`}
        >
          <i className="fa-solid fa-code"></i>
          View YAML
        </button>

        <button
          onClick={handleToggleWebUI}
          disabled={togglingWebUI}
          className={`${toolbarBtnBase} bg-gray-600 hover:bg-gray-700 text-white`}
        >
          {togglingWebUI ? (
            <i className="fa-solid fa-spinner fa-spin"></i>
          ) : (
            <i className="fa-solid fa-network-wired"></i>
          )}
          {togglingWebUI ? (isRegistered ? 'Unregistering...' : 'Registering...') : (isRegistered ? 'Unregister' : 'Register')}
        </button>
      </div>

      {yamlPreview && (
        <YamlPreviewModal yaml={yamlPreview} onClose={() => setYamlPreview(null)} />
      )}
    </>
  )
}

export default function ServiceDetailsHeader({ serviceName, config, runtime, transitioning, actions, onRename, onSuccess, onError }) {
  const navigate = useNavigate()
  const status = runtime?.status || 'not-created'
  const isRunning = status === 'running'
  const templateType = config?.template_type
  const [editing, setEditing] = useState(false)

  const canRename = !isRunning && !transitioning

  const handleRename = useCallback(async (newName) => {
    try {
      await onRename(newName)
      navigate(`/services/${newName}`, { replace: true })
    } catch (err) {
      onError(`Rename failed: ${err.message}`)
      throw err
    }
  }, [onRename, navigate, onError])

  return (
    <div className="bg-gray-800 border-b border-gray-700 px-6 py-4 -mx-6 -mt-6 mb-6">
      {/* Row 1: Identity */}
      <div className="flex items-center gap-4 flex-wrap">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-gray-400 hover:text-gray-200 cursor-pointer"
          aria-label="Back to services list"
        >
          <i className="fa-solid fa-arrow-left"></i>
          <span className="text-sm">Back to Services</span>
        </button>

        <div className="w-px h-6 bg-gray-700" />

        {editing ? (
          <InlineRename
            serviceName={serviceName}
            onRename={handleRename}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <>
            <h1 className="text-2xl font-bold text-white">{serviceName}</h1>
            <CopyButton text={serviceName} label="Copy service name" />
            <button
              onClick={() => setEditing(true)}
              disabled={!canRename}
              className="text-gray-400 hover:text-gray-200 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
              title={canRename ? 'Rename service' : 'Stop service to rename'}
            >
              <i className="fa-solid fa-pen text-sm"></i>
            </button>
          </>
        )}

        <StatusBadge status={status} transitioning={transitioning} />

        {templateType && <EngineBadge templateType={templateType} />}

        {config?.model_size_str && (
          <span className="text-xs text-gray-400">{config.model_size_str}</span>
        )}

        {(config?.model_path || config?.model_name) && (
          <span className="text-xs text-gray-500 font-mono break-all">
            {config.model_path || config.model_name}
          </span>
        )}
      </div>

      {/* Row 2: Metadata */}
      <MetadataRow config={config} runtime={runtime} />

      {/* Row 3: Toolbar */}
      <ToolbarRow
        config={config}
        runtime={runtime}
        transitioning={transitioning}
        actions={actions}
        onSuccess={onSuccess}
        onError={onError}
      />
    </div>
  )
}
