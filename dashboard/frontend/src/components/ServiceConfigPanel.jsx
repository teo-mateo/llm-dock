import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { fetchAPI } from '../api'

let nextParamId = 0

function paramsToArray(params) {
  return Object.entries(params || {}).map(([flag, value]) => ({
    id: nextParamId++,
    flag,
    value,
  }))
}

function paramsToObject(paramsArray) {
  const obj = {}
  for (const { flag, value } of paramsArray) {
    if (flag) obj[flag] = value
  }
  return obj
}

function paramsEqual(a, b) {
  const aObj = a || {}
  const bObj = b || {}
  const aKeys = Object.keys(aObj)
  const bKeys = Object.keys(bObj)
  if (aKeys.length !== bKeys.length) return false
  return aKeys.every(k => k in bObj && aObj[k] === bObj[k])
}

export default function ServiceConfigPanel({ config, serviceName, runtime, onSaved, onError, flagMetadata, onParamsChange, addFlagRef }) {
  const [port, setPort] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [params, setParams] = useState([])
  const [saving, setSaving] = useState(false)
  const [settingGlobalKey, setSettingGlobalKey] = useState(false)
  const [commandPreviewOpen, setCommandPreviewOpen] = useState(false)

  const initialized = useRef(false)

  // Initialize form from config
  useEffect(() => {
    if (config) {
      setPort(String(config.port || ''))
      setApiKey(config.api_key || '')
      setParams(paramsToArray(config.params))
      initialized.current = true
    }
  }, [config])

  // Notify parent of param flag changes for ParameterReference coordination
  const existingFlags = useMemo(() => params.map(p => p.flag), [params])
  const onParamsChangeRef = useRef(onParamsChange)
  onParamsChangeRef.current = onParamsChange
  useEffect(() => {
    if (onParamsChangeRef.current) onParamsChangeRef.current(existingFlags)
  }, [existingFlags])

  const duplicateFlags = useMemo(() => {
    const counts = {}
    for (const { flag } of params) {
      if (flag) counts[flag] = (counts[flag] || 0) + 1
    }
    return new Set(Object.keys(counts).filter(k => counts[k] > 1))
  }, [params])

  const hasDuplicates = duplicateFlags.size > 0

  const isDirty = useMemo(() => {
    if (!initialized.current || !config) return false
    if (port !== String(config.port || '')) return true
    if (apiKey !== (config.api_key || '')) return true
    return !paramsEqual(paramsToObject(params), config.params)
  }, [port, apiKey, params, config])

  const handleDiscard = useCallback(() => {
    if (config) {
      setPort(String(config.port || ''))
      setApiKey(config.api_key || '')
      setParams(paramsToArray(config.params))
    }
  }, [config])

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      const payload = {
        template_type: config.template_type,
        port: parseInt(port, 10),
        api_key: apiKey,
        params: paramsToObject(params),
      }
      if (config.model_path) payload.model_path = config.model_path
      if (config.model_name) payload.model_name = config.model_name
      if (config.alias) payload.alias = config.alias

      await fetchAPI(`/services/${serviceName}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })

      const wasRunning = runtime?.status === 'running'
      onSaved(wasRunning
        ? 'Configuration saved. Container will be recreated.'
        : 'Configuration saved.'
      )
    } catch (err) {
      onError(err.message)
    } finally {
      setSaving(false)
    }
  }, [config, port, apiKey, params, serviceName, runtime, onSaved, onError])

  const handleUseGlobalKey = useCallback(async () => {
    setSettingGlobalKey(true)
    try {
      const data = await fetchAPI(`/services/${serviceName}/set-global-api-key`, { method: 'PUT' })
      onSaved(data.message || 'API key updated to global key.')
    } catch (err) {
      onError(`Set global key failed: ${err.message}`)
    } finally {
      setSettingGlobalKey(false)
    }
  }, [serviceName, onSaved, onError])

  const handleParamFlagChange = useCallback((id, newFlag) => {
    setParams(prev => prev.map(p => p.id === id ? { ...p, flag: newFlag } : p))
  }, [])

  const handleParamValueChange = useCallback((id, newValue) => {
    setParams(prev => prev.map(p => p.id === id ? { ...p, value: newValue } : p))
  }, [])

  const handleParamRemove = useCallback((id) => {
    setParams(prev => prev.filter(p => p.id !== id))
  }, [])

  const justAddedIdRef = useRef(null)

  // Ensure there's always a trailing empty row
  useEffect(() => {
    const last = params[params.length - 1]
    if (!last || last.flag || last.value) {
      setParams(prev => [...prev, { id: nextParamId++, flag: '', value: '' }])
    }
  }, [params])

  const handleParamAdd = useCallback(() => {
    const id = nextParamId++
    justAddedIdRef.current = id
    setParams(prev => [...prev, { id, flag: '', value: '' }])
  }, [])

  // Expose addFlag for ParameterReference via ref
  const handleRefAdd = useCallback((flag, defaultValue) => {
    setParams(prev => {
      if (prev.some(p => p.flag === flag)) return prev
      return [...prev, { id: nextParamId++, flag, value: defaultValue }]
    })
  }, [])

  useEffect(() => {
    if (addFlagRef) addFlagRef.current = handleRefAdd
  }, [addFlagRef, handleRefAdd])

  const getTooltip = useCallback((flag) => {
    if (!flagMetadata || !flag) return null
    for (const meta of Object.values(flagMetadata)) {
      if (meta.cli === flag) return meta.description
    }
    return null
  }, [flagMetadata])

  if (!initialized.current && !config) return null

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-700 flex justify-between items-center">
        <h2 className="text-lg font-semibold text-gray-200">Configuration</h2>
        {isDirty && (
          <span className="text-yellow-400 text-sm flex items-center gap-1" role="status" aria-live="polite">
            <i className="fa-solid fa-circle-exclamation"></i>
            Unsaved changes
          </span>
        )}
      </div>

      <div className="p-5 space-y-5">
        {/* Editable fields */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2 text-gray-300" htmlFor="config-port">Port</label>
            <input
              id="config-port"
              type="number"
              value={port}
              onChange={e => setPort(e.target.value)}
              disabled={saving}
              className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2 text-gray-300" htmlFor="config-apikey">API Key</label>
            <div className="flex gap-2">
              <input
                id="config-apikey"
                type="text"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                disabled={saving}
                className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white font-mono text-sm focus:outline-none focus:border-blue-500 disabled:opacity-50"
              />
              <button
                onClick={handleUseGlobalKey}
                disabled={saving || settingGlobalKey}
                className="px-3 py-2 bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded text-xs text-gray-300 hover:text-white whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                title="Set API key to the global API key from .env"
              >
                {settingGlobalKey ? (
                  <i className="fa-solid fa-spinner fa-spin"></i>
                ) : (
                  'Use Global'
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Parameters section */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <label className="block text-sm font-medium text-gray-300">
              Parameters ({params.filter(p => p.flag || p.value).length})
            </label>
            <button
              onClick={handleParamAdd}
              disabled={saving}
              className="text-sm text-blue-400 hover:text-blue-300 disabled:opacity-50 cursor-pointer"
            >
              <i className="fa-solid fa-plus mr-1"></i>Add parameter
            </button>
          </div>
          <div className="space-y-0.5">
            {params.map(({ id, flag, value }, idx) => {
              const tooltip = getTooltip(flag)
              const isDuplicate = flag && duplicateFlags.has(flag)
              const isTrailingEmpty = idx === params.length - 1 && !flag && !value
              return (
                <div key={id} className="flex items-center gap-2 rounded px-3 py-1">
                  <input
                    ref={el => { if (el && justAddedIdRef.current === id) { el.focus(); justAddedIdRef.current = null } }}
                    value={flag}
                    onChange={e => handleParamFlagChange(id, e.target.value)}
                    disabled={saving}
                    placeholder="-flag"
                    className={`bg-gray-700 border rounded px-2 py-1 font-mono text-sm w-40 text-white focus:outline-none disabled:opacity-50 ${isDuplicate ? 'border-red-500 focus:border-red-500' : 'border-gray-600 focus:border-blue-500'}`}
                    title={isDuplicate ? 'Duplicate flag' : tooltip || undefined}
                  />
                  <input
                    value={value}
                    onChange={e => handleParamValueChange(id, e.target.value)}
                    disabled={saving}
                    placeholder="value"
                    className="flex-1 bg-gray-700 border border-gray-600 rounded px-2 py-1 font-mono text-sm text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
                  />
                  <button
                    onClick={() => handleParamRemove(id)}
                    disabled={saving || isTrailingEmpty}
                    className={`disabled:opacity-50 cursor-pointer ${isTrailingEmpty ? 'invisible' : 'text-gray-500 hover:text-red-400'}`}
                    aria-label={`Remove parameter ${flag || '(empty)'}`}
                  >
                    <i className="fa-solid fa-xmark"></i>
                  </button>
                </div>
              )
            })}
            {hasDuplicates && (
              <p className="text-red-400 text-xs mt-1 px-3">
                Duplicate flags: {[...duplicateFlags].join(', ')}
              </p>
            )}
          </div>
        </div>

        {/* Command preview */}
        <div>
          <button
            onClick={() => setCommandPreviewOpen(prev => !prev)}
            className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-200 cursor-pointer"
          >
            <i className={`fa-solid ${commandPreviewOpen ? 'fa-chevron-up' : 'fa-chevron-down'}`}></i>
            Command Preview
          </button>
          {commandPreviewOpen && (
            <div className="mt-2 bg-gray-900 rounded p-4 font-mono text-xs text-gray-300 whitespace-pre-wrap">
              {renderCommandPreview(config, apiKey, params)}
            </div>
          )}
        </div>

        {/* Save/Discard buttons */}
        <div className="flex gap-3 pt-4 border-t border-gray-700">
          <button
            onClick={handleDiscard}
            disabled={!isDirty || saving}
            className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded font-semibold text-sm disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            Discard
          </button>
          <button
            onClick={handleSave}
            disabled={!isDirty || saving || hasDuplicates}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-semibold text-sm disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {saving ? (
              <>
                <i className="fa-solid fa-spinner fa-spin"></i>
                Saving...
              </>
            ) : (
              <>
                <i className="fa-solid fa-save"></i>
                Save
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

function renderCommandPreview(config, apiKey, params) {
  if (!config) return ''
  const parts = []

  if (config.template_type === 'llamacpp') {
    parts.push('llama-server')
    if (config.model_path) parts.push(`-m ${config.model_path}`)
    parts.push(`--port 8080`)
    parts.push(`--api-key ${apiKey || '***'}`)
  } else {
    parts.push('vllm serve')
    if (config.model_name) parts.push(config.model_name)
    parts.push(`--port 8000`)
    parts.push(`--api-key ${apiKey || '***'}`)
  }

  for (const { flag, value } of params) {
    if (!flag) continue
    if (value) {
      parts.push(`${flag} ${value}`)
    } else {
      parts.push(flag)
    }
  }

  return parts.join(' \\\n  ')
}
