import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchAPI } from '../api'
import { generateServiceName, aliasFromModelName } from '../utils/serviceNaming'
import { renderCommandPreview } from './commandPreview'
import ParameterReference from './ParameterReference'

const ENGINES = [
  { type: 'llamacpp', label: 'llama.cpp', hint: 'GGUF file' },
  { type: 'ik_llamacpp', label: 'ik llama.cpp', hint: 'GGUF file (ik fork)' },
  { type: 'vllm', label: 'vLLM', hint: 'HuggingFace org/name' },
  { type: 'ds4', label: 'ds4', hint: 'DeepSeek V4 Flash file' },
  { type: 'tabbyapi', label: 'TabbyAPI', hint: 'EXL3 model directory' },
  { type: 'ninfer', label: 'NInfer', hint: '.ninfer artifact' },
]

// Engines whose model is a file on disk rather than a HuggingFace repo id.
const FILE_ENGINES = new Set(['llamacpp', 'ik_llamacpp', 'ds4', 'tabbyapi', 'ninfer'])

// Engines for which the discovered-file picker is meaningful; TabbyAPI wants a
// model directory and NInfer wants .ninfer artifacts, neither of which
// discovery scans.
const GGUF_PICKER_ENGINES = new Set(['llamacpp', 'ik_llamacpp', 'ds4'])

const PORT_FIRST = 3301
const PORT_LAST = 3399

// Sharded GGUFs load from the first shard (the rest must sit beside it), so
// only shard 1 is ever offered as a model — offering shard 3 of 4 creates a
// service that can never load. mmproj projectors are not models either.
const SHARD_RE = /-\d{5}-of-(\d{5})\.gguf$/i

let nextParamId = 0

function paramsToObject(params) {
  const obj = {}
  for (const { flag, value } of params) {
    if (flag) obj[flag] = value
  }
  return obj
}

function nextFreePort(services) {
  const used = new Set((services || []).map(s => s.host_port).filter(Boolean))
  for (let p = PORT_FIRST; p <= PORT_LAST; p++) {
    if (!used.has(p)) return p
  }
  return PORT_FIRST
}

// Host paths back to container paths, mirroring _CONTAINER_PATH_MAP in
// model_discovery.py — a picked file is sent as its in-container path.
function toContainerPath(hostPath) {
  return String(hostPath)
    .replace(/^\/home\/[^/]+\/\.cache\/huggingface/, '/hf-cache')
    .replace(/^\/home\/[^/]+\/\.cache\/models/, '/local-models')
}

function KeyCopy({ value }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="flex items-center gap-2 bg-app border border-border rounded px-3 py-2">
      <code className="text-success-fg text-xs break-all flex-1">{value}</code>
      <button
        onClick={async () => {
          // Clipboard APIs are only available on secure origins (localhost
          // or https); a LAN-IP deployment would otherwise throw here.
          try {
            await navigator.clipboard.writeText(value)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
          } catch {
            // The key stays fully visible in the <code> — copy is a convenience.
          }
        }}
        className="text-fg-muted hover:text-fg text-lg leading-none cursor-pointer shrink-0"
        title="Copy"
      >
        {copied ? '✓' : '⧉'}
      </button>
    </div>
  )
}

export default function CreateServiceModal({ services, onClose, onCreated }) {
  const navigate = useNavigate()
  const [templateType, setTemplateType] = useState('llamacpp')
  const [alias, setAlias] = useState('')
  const [modelPath, setModelPath] = useState('')
  const [modelName, setModelName] = useState('')
  const [port, setPort] = useState(() => String(nextFreePort(services)))
  const [apiKey, setApiKey] = useState('')
  const [reasoningLevels, setReasoningLevels] = useState('')
  const [params, setParams] = useState([{ id: nextParamId++, flag: '', value: '' }])
  const [flagMetadata, setFlagMetadata] = useState(null)
  const [models, setModels] = useState(null)
  const [modelsError, setModelsError] = useState(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [errorDetails, setErrorDetails] = useState([])
  const [result, setResult] = useState(null)

  const isFileEngine = FILE_ENGINES.has(templateType)

  // Flag metadata per engine, same fetch the details page runs for its
  // ParameterReference; the generation guard drops stale responses from a
  // previous engine.
  const metadataFetchId = useRef(0)
  useEffect(() => {
    if (!templateType) return
    const id = ++metadataFetchId.current
    fetchAPI(`/flag-metadata/${templateType}`)
      .then(data => { if (metadataFetchId.current === id) setFlagMetadata(data.optional_flags || {}) })
      .catch(() => { if (metadataFetchId.current === id) setFlagMetadata({}) })
  }, [templateType])

  // Model discovery for the file pickers — advisory only, the manual inputs
  // always work, so a scan failure degrades the picker, not the form.
  useEffect(() => {
    let cancelled = false
    fetchAPI('/system/info')
      .then(data => { if (!cancelled) setModels(data.models || []) })
      .catch(e => { if (!cancelled) setModelsError(e.message) })
    return () => { cancelled = true }
  }, [])

  const ggufChoices = useMemo(() => {
    if (!models) return []
    const out = []
    const seen = new Set()
    for (const m of models) {
      for (const f of m.files || []) {
        if (!/\.gguf$/i.test(f.name) || /mmproj/i.test(f.name)) continue
        const match = f.name.match(SHARD_RE)
        const modelName = m.full_name || m.name
        if (match) {
          const key = `${modelName}|${f.name.replace(SHARD_RE, '')}`
          if (!seen.has(key)) {
            seen.add(key)
            out.push({
              label: `${modelName} — ${f.name.replace(SHARD_RE, '')}`,
              modelName,
              size: '',
              path: toContainerPath(f.path),
              shards: Number(match[1]),
            })
          }
          continue
        }
        out.push({
          label: `${modelName} — ${f.name}`,
          modelName,
          size: f.size_str,
          path: toContainerPath(f.path),
          shards: 1,
        })
      }
    }
    return out
  }, [models])

  const hfChoices = useMemo(() => {
    if (!models) return []
    return models
      .filter(m => m.type === 'huggingface' && !m.quantization)
      .filter(m => !(m.files || []).some(f => /\.gguf$/i.test(f.name)))
      .map(m => ({ name: m.name, label: m.size_str ? `${m.name} (${m.size_str})` : m.name }))
  }, [models])

  const existingFlags = useMemo(
    () => params.filter(p => p.flag).map(p => p.flag.trim()),
    [params]
  )

  const handleParamChange = useCallback((id, field, value) => {
    setParams(prev => prev.map(p => p.id === id ? { ...p, [field]: value } : p))
  }, [])

  const handleParamAdd = useCallback(() => {
    setParams(prev => [...prev, { id: nextParamId++, flag: '', value: '' }])
  }, [])

  const handleParamRemove = useCallback((id) => {
    setParams(prev => prev.filter(p => p.id !== id))
  }, [])

  const handleAddFlag = useCallback((flag, defaultValue) => {
    setParams(prev => {
      if (prev.some(p => p.flag === flag)) return prev
      return [...prev, { id: nextParamId++, flag, value: defaultValue }]
    })
  }, [])

  const pickModel = useCallback((value, suggested) => {
    if (isFileEngine) {
      setModelPath(value)
      if (suggested) setAlias(prev => prev || suggested)
    } else {
      setModelName(value)
      if (suggested) setAlias(prev => prev || suggested)
    }
  }, [isFileEngine])

  const serviceNamePreview = alias.trim() ? generateServiceName(templateType, alias) : ''

  const portValid = /^\d+$/.test(port) && Number(port) >= 1024 && Number(port) <= 65535
  const modelFilled = isFileEngine ? modelPath.trim() : modelName.trim()
  const canSubmit = !submitting && !!alias.trim() && portValid && !!modelFilled

  // Escape closes the modal on both views; the modal is the only dialog on
  // the page while mounted, so no open-state guard is needed.
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') closeRef.current() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const handleCreate = useCallback(async () => {
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    setErrorDetails([])
    try {
      const payload = {
        template_type: templateType,
        alias: alias.trim(),
        port: Number(port),
        params: paramsToObject(params),
      }
      if (isFileEngine) payload.model_path = modelPath.trim()
      else payload.model_name = modelName.trim()
      if (apiKey.trim()) payload.api_key = apiKey.trim()
      if (reasoningLevels.trim()) payload.reasoning_levels = reasoningLevels.trim()

      const response = await fetchAPI('/services', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setResult(response)
      onCreated?.()
    } catch (e) {
      setError(e.message)
      setErrorDetails(Array.isArray(e.details) ? e.details : [])
    } finally {
      setSubmitting(false)
    }
  }, [canSubmit, templateType, alias, port, params, isFileEngine, modelPath, modelName, apiKey, reasoningLevels, onCreated])

  const handleOpenService = useCallback(() => {
    onClose()
    navigate(`/services/${result.service_name}`)
  }, [result, onClose, navigate])

  const previewConfig = isFileEngine
    ? { template_type: templateType, model_path: modelPath.trim() }
    : { template_type: templateType, model_name: modelName.trim() }

  const inputClass = 'w-full bg-surface-strong border border-border-strong rounded px-3 py-2 text-fg focus:outline-none focus:border-accent disabled:opacity-50'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={result ? 'Service created' : 'New service'}
        className="bg-surface rounded-lg border border-border max-w-5xl w-full max-h-[85vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-border flex justify-between items-center flex-shrink-0">
          <h3 className="text-lg font-semibold text-fg">
            {result ? 'Service Created' : 'New Service'}
          </h3>
          <button onClick={onClose} className="text-fg-muted hover:text-fg cursor-pointer" aria-label="Close">✕</button>
        </div>

        <div className="px-5 py-4 overflow-auto space-y-4 text-sm">
          {result ? (
            <>
              <p className="text-fg">
                <span className="font-semibold">{result.service_name}</span> is created on port{' '}
                <span className="font-mono">{result.port}</span> and registered in the compose file.
                It is stopped — start it from the details page.
              </p>
              <div>
                <p className="text-fg-muted mb-1">API key:</p>
                <KeyCopy value={result.api_key} />
              </div>
              {result.warnings?.length > 0 && (
                <div className="bg-warning-subtle border border-warning text-warning-fg rounded px-3 py-2">
                  <p className="font-medium">⚠ {result.warnings.length} flag(s) not in the engine's recorded surface</p>
                  <ul className="mt-1 text-xs font-mono space-y-0.5">
                    {result.warnings.map(w => <li key={w}>• {w}</li>)}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_260px] gap-4">
            <div className="min-w-0 space-y-4">
              {/* Engine */}
              <div>
                <label className="block text-sm font-medium mb-2 text-fg-muted">Engine *</label>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {ENGINES.map(engine => (
                    <label
                      key={engine.type}
                      className={`flex items-start gap-2 rounded border px-3 py-2 cursor-pointer transition-colors ${
                        templateType === engine.type
                          ? 'border-accent bg-surface-strong'
                          : 'border-border hover:bg-surface-muted'
                      }`}
                    >
                      <input
                        type="radio"
                        name="create-engine"
                        value={engine.type}
                        checked={templateType === engine.type}
                        onChange={() => setTemplateType(engine.type)}
                        className="mt-0.5"
                      />
                      <span>
                        <span className="block text-sm text-fg">{engine.label}</span>
                        <span className="block text-xs text-fg-subtle">{engine.hint}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Model */}
              <div>
                {isFileEngine ? (
                  <>
                    <label className="block text-sm font-medium mb-2 text-fg-muted" htmlFor="create-model-path">
                      Model path (container) *
                    </label>
                    {GGUF_PICKER_ENGINES.has(templateType) && (
                      <select
                        aria-label="Pick a discovered file"
                        value=""
                        onChange={e => {
                          if (!e.target.value) return
                          const choice = ggufChoices[Number(e.target.value)]
                          pickModel(choice.path, aliasFromModelName(choice.modelName))
                        }}
                        className={`${inputClass} text-xs mb-1 ${models ? '' : 'opacity-50'}`}
                      >
                        <option value="">
                          {modelsError ? 'Pick a file — discovery unavailable' : models ? 'Pick a discovered file…' : 'Loading discovered files…'}
                        </option>
                        {ggufChoices.map((c, i) => (
                          <option key={`${c.path}-${i}`} value={i}>{c.label}{c.shards > 1 ? ` — ${c.shards} shards` : c.size ? ` — ${c.size}` : ''}</option>
                        ))}
                      </select>
                    )}
                    <input
                      id="create-model-path"
                      type="text"
                      value={modelPath}
                      onChange={e => setModelPath(e.target.value)}
                      placeholder={templateType === 'tabbyapi'
                        ? '/hf-cache/… or /local-models/… (model directory)'
                        : '/hf-cache/… or /local-models/…'}
                      className={`${inputClass} font-mono text-sm`}
                    />
                    <p className="mt-1 text-xs text-fg-subtle">
                      In-container path: the HF cache is <span className="font-mono">/hf-cache/…</span>,
                      <span className="font-mono">~/.cache/models</span> is <span className="font-mono">/local-models/…</span>.
                    </p>
                  </>
                ) : (
                  <>
                    <label className="block text-sm font-medium mb-2 text-fg-muted" htmlFor="create-model-name">
                      HuggingFace model (org/name) *
                    </label>
                    <select
                      aria-label="Pick a cached model"
                      value=""
                      onChange={e => {
                        if (!e.target.value) return
                        const name = hfChoices[Number(e.target.value)].name
                        pickModel(name, aliasFromModelName(name))
                      }}
                      className={`${inputClass} text-xs mb-1 ${models ? '' : 'opacity-50'}`}
                    >
                      <option value="">
                        {modelsError ? 'Pick a cached model — discovery unavailable' : models ? 'Pick a cached model…' : 'Loading cached models…'}
                      </option>
                      {hfChoices.map((c, i) => (
                        <option key={c.name} value={i}>{c.label}</option>
                      ))}
                    </select>
                    <input
                      id="create-model-name"
                      type="text"
                      value={modelName}
                      onChange={e => setModelName(e.target.value)}
                      placeholder="org/model-name"
                      className={`${inputClass} font-mono text-sm`}
                    />
                    <p className="mt-1 text-xs text-fg-subtle">
                      Must already be in the local HF cache — containers run with <span className="font-mono">HF_HUB_OFFLINE=1</span>.
                    </p>
                  </>
                )}
              </div>

              {/* Alias + name preview */}
              <div>
                <label className="block text-sm font-medium mb-2 text-fg-muted" htmlFor="create-alias">
                  Service alias *
                </label>
                <input
                  id="create-alias"
                  type="text"
                  value={alias}
                  onChange={e => setAlias(e.target.value)}
                  placeholder="qwen3-8b"
                  className={`${inputClass} font-mono text-sm`}
                />
                <p className="mt-1 text-xs text-fg-subtle">
                  Service name:{' '}
                  <span className="font-mono text-fg-muted">
                    {serviceNamePreview || '—'}
                  </span>
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2 text-fg-muted" htmlFor="create-port">
                    Port *
                  </label>
                  <input
                    id="create-port"
                    type="number"
                    min="1024"
                    max="65535"
                    value={port}
                    onChange={e => setPort(e.target.value)}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2 text-fg-muted" htmlFor="create-api-key">
                    API key
                  </label>
                  <input
                    id="create-api-key"
                    type="text"
                    value={apiKey}
                    onChange={e => setApiKey(e.target.value)}
                    placeholder="auto-generate if empty"
                    className={`${inputClass} font-mono text-xs`}
                  />
                </div>
                <div className="col-span-2">
                  <label
                    className="block text-sm font-medium mb-2 text-fg-muted"
                    htmlFor="create-reasoning-levels"
                    title="Comma-separated level names this model accepts, shown verbatim in chat. They are instructions to the model's chat template, not token budgets — an undeclared token is rejected by the template, so list only what the model takes. Leave empty to offer nothing."
                  >
                    Reasoning levels
                  </label>
                  <input
                    id="create-reasoning-levels"
                    type="text"
                    value={reasoningLevels}
                    onChange={e => setReasoningLevels(e.target.value)}
                    placeholder="off,low,medium,xhigh"
                    className={`${inputClass} font-mono text-sm`}
                  />
                  <p className="mt-1 text-xs text-fg-subtle">
                    Comma separated, lowercase. Empty means no reasoning control for this model.
                  </p>
                </div>
              </div>

              {/* Parameters */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-medium text-fg-muted">
                    Parameters ({params.filter(p => p.flag || p.value).length})
                  </label>
                  <button
                    type="button"
                    onClick={handleParamAdd}
                    className="text-sm text-accent-fg hover:text-accent-fg-hover cursor-pointer"
                  >
                    <i className="fa-solid fa-plus mr-1"></i>Add parameter
                  </button>
                </div>
                <div className="space-y-0.5">
                  {params.map(({ id, flag, value }) => (
                    <div key={id} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={flag}
                        onChange={e => handleParamChange(id, 'flag', e.target.value)}
                        placeholder="-flag"
                        aria-label="Parameter flag"
                        className="w-32 sm:w-44 shrink-0 bg-surface-strong border border-border-strong rounded px-2 py-1 font-mono text-sm text-fg focus:outline-none focus:border-accent"
                      />
                      <input
                        type="text"
                        value={value}
                        onChange={e => handleParamChange(id, 'value', e.target.value)}
                        placeholder="value (empty = bare flag)"
                        aria-label="Parameter value"
                        className="flex-1 min-w-0 bg-surface-strong border border-border-strong rounded px-2 py-1 font-mono text-sm text-fg focus:outline-none focus:border-accent"
                      />
                      <button
                        type="button"
                        onClick={() => handleParamRemove(id)}
                        className="text-fg-subtle hover:text-danger-fg cursor-pointer"
                        aria-label={`Remove parameter ${flag || '(empty)'}`}
                      >
                        <i className="fa-solid fa-xmark"></i>
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Command preview */}
              <div>
                <button
                  type="button"
                  onClick={() => setPreviewOpen(prev => !prev)}
                  className="flex items-center gap-2 text-sm text-fg-muted hover:text-fg cursor-pointer"
                >
                  <i className={`fa-solid ${previewOpen ? 'fa-chevron-up' : 'fa-chevron-down'}`}></i>
                  Command Preview
                </button>
                {previewOpen && (
                  <div className="mt-2 bg-app rounded p-4 font-mono text-xs text-fg-muted whitespace-pre-wrap">
                    {renderCommandPreview(previewConfig, apiKey, params)}
                  </div>
                )}
              </div>

              {error && (
                <div className="bg-danger-subtle border border-danger text-danger-fg rounded px-3 py-2">
                  <p>{error}</p>
                  {errorDetails.length > 0 && (
                    <ul className="mt-1 text-xs font-mono space-y-0.5">
                      {errorDetails.map(d => <li key={d}>• {d}</li>)}
                    </ul>
                  )}
                </div>
              )}
            </div>
            {flagMetadata && Object.keys(flagMetadata).length > 0 && (
              <div className="h-72 md:sticky md:top-0 md:h-[26rem] rounded-lg overflow-hidden">
                <ParameterReference
                  flagMetadata={flagMetadata}
                  existingFlags={existingFlags}
                  onAddFlag={handleAddFlag}
                />
              </div>
            )}
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-border flex justify-end gap-3 flex-shrink-0">
          {result ? (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 bg-surface-strong hover:bg-surface-muted text-fg text-sm rounded transition-colors cursor-pointer"
              >
                Done
              </button>
              <button
                onClick={handleOpenService}
                className="px-4 py-2 bg-accent-strong hover:bg-accent-strong text-white text-sm rounded transition-colors cursor-pointer"
              >
                Open service
              </button>
            </>
          ) : (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 bg-surface-strong hover:bg-surface-muted text-fg text-sm rounded transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!canSubmit}
                className="inline-flex items-center gap-2 px-4 py-2 bg-accent-strong hover:bg-accent-strong text-white text-sm rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                {submitting ? (
                  <>
                    <i className="fa-solid fa-spinner fa-spin"></i>
                    Creating…
                  </>
                ) : (
                  <>
                    <i className="fa-solid fa-plus"></i>
                    Create service
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
