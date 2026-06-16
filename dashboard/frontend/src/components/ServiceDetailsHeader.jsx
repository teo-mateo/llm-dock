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
      className="text-fg-muted hover:text-fg cursor-pointer"
      aria-label={label}
      title={label}
    >
      <i className={`fa-solid ${copied ? 'fa-check text-success-fg' : 'fa-copy'} text-sm`}></i>
    </button>
  )
}

function StatusBadge({ status, transitioning }) {
  let bgClass, textClass, borderClass, label

  if (transitioning) {
    bgClass = 'bg-warning-subtle'
    textClass = 'text-warning-fg'
    borderClass = 'border-warning'
    label = transitioning === 'starting' ? 'Starting...' : transitioning === 'stopping' ? 'Stopping...' : 'Restarting...'
  } else if (status === 'running') {
    bgClass = 'bg-success-subtle'
    textClass = 'text-success-fg'
    borderClass = 'border-success'
    label = 'Running'
  } else if (status === 'exited') {
    bgClass = 'bg-danger-subtle'
    textClass = 'text-danger-fg'
    borderClass = 'border-danger'
    label = 'Stopped'
  } else {
    bgClass = 'bg-surface-muted'
    textClass = 'text-fg-muted'
    borderClass = 'border-border-strong'
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
        transitioning ? 'bg-warning' : status === 'running' ? 'bg-success' : status === 'exited' ? 'bg-danger' : 'bg-fg-muted'
      }`} />
      {label}
    </span>
  )
}

function EngineBadge({ templateType }) {
  const engineMap = {
    llamacpp: { label: 'llama.cpp', classes: 'bg-badge-llamacpp-bg text-badge-llamacpp-fg' },
    vllm: { label: 'vLLM', classes: 'bg-badge-vllm-bg text-badge-vllm-fg' },
    ds4: { label: 'DS4', classes: 'bg-badge-ds4-bg text-badge-ds4-fg' },
  }
  const engine = engineMap[templateType] || { label: templateType, classes: 'bg-badge-neutral-bg text-badge-neutral-fg' }

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
        className="bg-surface-strong border border-border-strong rounded px-2 py-1 text-xl font-bold text-fg focus:outline-none focus:border-accent disabled:opacity-50"
        onKeyDown={e => e.key === 'Escape' && onCancel()}
      />
      <button
        type="submit"
        disabled={renaming}
        className="text-success-fg hover:text-success-fg disabled:opacity-50 cursor-pointer"
        title="Confirm rename"
      >
        <i className={`fa-solid ${renaming ? 'fa-spinner fa-spin' : 'fa-check'}`}></i>
      </button>
      <button
        type="button"
        onClick={onCancel}
        disabled={renaming}
        className="text-fg-muted hover:text-fg disabled:opacity-50 cursor-pointer"
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
      <div className="bg-surface rounded-lg border border-border max-w-3xl w-full max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-border flex justify-between items-center">
          <h3 className="text-lg font-semibold text-fg">Docker Compose YAML</h3>
          <div className="flex items-center gap-3">
            <CopyButton text={yaml} label="Copy YAML" />
            <button onClick={onClose} className="text-fg-muted hover:text-fg cursor-pointer" aria-label="Close">
              <i className="fa-solid fa-xmark"></i>
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-auto p-5">
          <pre className="font-mono text-sm text-fg-muted whitespace-pre-wrap">{yaml}</pre>
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
    <div className="flex items-center gap-4 flex-wrap pt-3 mt-3 border-t border-border">
      {/* Port */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-fg-muted">Port:</span>
        {port ? (
          <>
            {isRunning ? (
              <a
                href={`http://${window.location.hostname}:${port}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-mono text-accent-fg hover:text-accent-fg-hover"
              >
                {port}
              </a>
            ) : (
              <span className="text-xs font-mono text-fg">{port}</span>
            )}
            {isPublicPort && (
              <span className="text-success-fg" title="Public port (3301)">
                <i className="fa-solid fa-globe text-xs"></i>
              </span>
            )}
          </>
        ) : (
          <span className="text-xs text-fg-subtle">N/A</span>
        )}
      </div>

      {/* API Key */}
      {apiKey && (
        <>
          <div className="w-px h-4 bg-surface-strong" />
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-fg-muted">API Key:</span>
            <span className="text-xs font-mono text-fg">{apiKey.slice(0, 16)}...</span>
            <CopyButton text={apiKey} label="Copy API key" />
          </div>
        </>
      )}

      {/* Container ID */}
      {containerId && (
        <>
          <div className="w-px h-4 bg-surface-strong" />
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-fg-muted">Container:</span>
            <span className="text-xs font-mono text-fg">{containerId.slice(0, 7)}</span>
            <CopyButton text={containerId} label="Copy container ID" />
          </div>
        </>
      )}

      {/* Open WebUI status */}
      <>
        <div className="w-px h-4 bg-surface-strong" />
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-fg-muted">WebUI:</span>
          {isRegistered ? (
            <span className="text-xs text-success-fg">Registered</span>
          ) : (
            <span className="text-xs text-fg-subtle">Not registered</span>
          )}
        </div>
      </>

      {/* Exit code */}
      {status === 'exited' && runtime?.exit_code != null && (
        <>
          <div className="w-px h-4 bg-surface-strong" />
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-fg-muted">Exit code:</span>
            <span className="text-xs text-fg">{runtime.exit_code}</span>
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
      <div className="flex items-center gap-2 flex-wrap mt-3 pt-3 border-t border-border">
        {/* Group 1: Lifecycle */}
        {isRunning ? (
          <>
            <button
              onClick={() => handleLifecycleAction(actions.stop)}
              disabled={disabled}
              className={`${toolbarBtnBase} bg-danger hover:bg-danger text-white`}
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
              className={`${toolbarBtnBase} bg-warning hover:bg-warning text-white`}
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
            className={`${toolbarBtnBase} bg-success hover:bg-success text-white`}
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
        <div className="w-px h-5 bg-surface-muted mx-1" />

        {/* Group 2: Actions */}
        {!isPublicPort ? (
          <button
            onClick={handleSetPublicPort}
            disabled={settingPublicPort}
            className={`${toolbarBtnBase} bg-surface-muted hover:bg-surface-strong text-fg`}
          >
            {settingPublicPort ? (
              <i className="fa-solid fa-spinner fa-spin"></i>
            ) : (
              <i className="fa-solid fa-globe"></i>
            )}
            {settingPublicPort ? 'Setting...' : 'Set as Public'}
          </button>
        ) : (
          <span className="px-3 py-1.5 rounded text-xs font-medium inline-flex items-center gap-1.5 bg-success-subtle text-success-fg border border-success">
            <i className="fa-solid fa-globe"></i>
            Public (3301)
          </span>
        )}

        <button
          onClick={handleViewYaml}
          className={`${toolbarBtnBase} bg-surface-muted hover:bg-surface-strong text-fg`}
        >
          <i className="fa-solid fa-code"></i>
          View YAML
        </button>

        <button
          onClick={handleToggleWebUI}
          disabled={togglingWebUI}
          className={`${toolbarBtnBase} bg-surface-muted hover:bg-surface-strong text-fg`}
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
    <div className="bg-surface border-b border-border px-6 py-4 -mx-6 -mt-6 mb-6">
      {/* Row 1: Identity */}
      <div className="flex items-center gap-4 flex-wrap">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-fg-muted hover:text-fg cursor-pointer"
          aria-label="Back to services list"
        >
          <i className="fa-solid fa-arrow-left"></i>
          <span className="text-sm">Back to Services</span>
        </button>

        <div className="w-px h-6 bg-surface-strong" />

        {editing ? (
          <InlineRename
            serviceName={serviceName}
            onRename={handleRename}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <>
            <h1 className="text-2xl font-bold text-fg">{serviceName}</h1>
            <CopyButton text={serviceName} label="Copy service name" />
            <button
              onClick={() => setEditing(true)}
              disabled={!canRename}
              className="text-fg-muted hover:text-fg disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
              title={canRename ? 'Rename service' : 'Stop service to rename'}
            >
              <i className="fa-solid fa-pen text-sm"></i>
            </button>
          </>
        )}

        <StatusBadge status={status} transitioning={transitioning} />

        {templateType && <EngineBadge templateType={templateType} />}

        {config?.model_size_str && (
          <span className="text-xs text-fg-muted">{config.model_size_str}</span>
        )}

        {(config?.model_path || config?.model_name) && (
          <span className="text-xs text-fg-subtle font-mono break-all">
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
