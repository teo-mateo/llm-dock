import { useState } from 'react'
import useProviderSettings from '../../hooks/useProviderSettings'

const INPUT = 'w-full bg-surface border border-border rounded px-3 py-2 text-xs text-fg focus:outline-none focus:border-accent-strong'
const BTN = 'text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong text-fg disabled:opacity-50'
const BTN_PRIMARY = 'text-xs px-2 py-1 rounded bg-accent-strong text-white hover:bg-accent-hover disabled:opacity-50'
const PROVIDER_ID_RE = /^[a-z][a-z0-9-]{1,31}$/

function KeyBadge({ provider }) {
  if (provider.key_source === 'stored') {
    return <span className="text-xs text-success-fg"><i className="fa-solid fa-key mr-1"></i>key stored</span>
  }
  if (provider.key_source === 'env') {
    return <span className="text-xs text-success-fg"><i className="fa-solid fa-key mr-1"></i>key from ${provider.api_key_env}</span>
  }
  return (
    <span className="text-xs text-warning-fg">
      <i className="fa-solid fa-triangle-exclamation mr-1"></i>
      no API key{provider.api_key_env ? ` ($${provider.api_key_env} is not set for the dashboard)` : ''}
    </span>
  )
}

function ProviderForm({ initial, isNew, existingIds, presets = [], onSave, onCancel }) {
  const [id, setId] = useState(initial.id || '')
  const [name, setName] = useState(initial.name || '')
  const [baseUrl, setBaseUrl] = useState(initial.base_url || '')
  const [apiKey, setApiKey] = useState('')
  const [removeKey, setRemoveKey] = useState(false)
  const [envName, setEnvName] = useState(initial.api_key_env || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [preset, setPreset] = useState('')

  const applyPreset = (presetId) => {
    setPreset(presetId)
    const p = presets.find(x => x.id === presetId) || {}
    setId(p.id || '')
    setName(p.name || '')
    setBaseUrl(p.base_url || '')
    setEnvName(p.api_key_env || '')
  }

  const idError = isNew && id && (!PROVIDER_ID_RE.test(id) || id === 'openrouter' || existingIds.includes(id))
  const canSave = !saving && name.trim() && baseUrl.trim() && (!isNew || (id && !idError))

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    const body = { name: name.trim(), base_url: baseUrl.trim(), api_key_env: envName.trim() }
    if (apiKey.trim()) body.api_key = apiKey.trim()
    else if (removeKey) body.api_key = null
    try {
      await onSave(id, body)
    } catch (err) {
      setError(err.message || 'Save failed')
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 border border-border rounded p-4 bg-surface-muted">
      {isNew && presets.length > 0 && (
        <label className="block">
          <span className="text-xs text-fg-muted">Start from</span>
          <select className={INPUT} value={preset} onChange={e => applyPreset(e.target.value)} aria-label="Start from">
            <option value="">Custom (any OpenAI-compatible API)</option>
            {presets.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
      )}
      {isNew && (
        <label className="block">
          <span className="text-xs text-fg-muted">Id — the prefix in model names, e.g. <code>{id || 'acme'}:&lt;model&gt;</code></span>
          <input className={INPUT} value={id} onChange={e => setId(e.target.value.toLowerCase())} placeholder="acme" />
          {idError && <span className="text-xs text-danger-fg">2–32 chars of a–z, 0–9, “-”, starting with a letter; not already used; not “openrouter”.</span>}
        </label>
      )}
      <label className="block">
        <span className="text-xs text-fg-muted">Name</span>
        <input className={INPUT} value={name} onChange={e => setName(e.target.value)} placeholder="Acme AI" />
      </label>
      <label className="block">
        <span className="text-xs text-fg-muted">Base URL (OpenAI-compatible, ending in /v1)</span>
        <input className={INPUT} value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" />
      </label>
      <label className="block">
        <span className="text-xs text-fg-muted">API key {initial.key_source === 'stored' ? '— leave blank to keep the stored key' : ''}</span>
        <input className={INPUT} type="password" autoComplete="off" value={apiKey}
               onChange={e => { setApiKey(e.target.value); setRemoveKey(false) }} placeholder="paste key" />
      </label>
      {initial.key_source === 'stored' && !apiKey && (
        <label className="flex items-center gap-2 text-xs text-fg-muted">
          <input type="checkbox" checked={removeKey} onChange={e => setRemoveKey(e.target.checked)} />
          Remove the stored key
        </label>
      )}
      <label className="block">
        <span className="text-xs text-fg-muted">
          Or read the key from an environment variable (used when no key is stored).
          It must be visible to the dashboard process — e.g. in <code>dashboard/.env</code> — not just your shell.
        </span>
        <input className={INPUT} value={envName} onChange={e => setEnvName(e.target.value.toUpperCase())} placeholder="ACME_API_KEY" />
      </label>
      {error && <div className="text-xs text-danger-fg bg-danger-subtle border border-danger rounded px-3 py-2">{error}</div>}
      <div className="flex gap-2">
        <button type="submit" disabled={!canSave} className={BTN_PRIMARY}>{saving ? 'Saving…' : 'Save'}</button>
        <button type="button" onClick={onCancel} className={BTN}>Cancel</button>
      </div>
    </form>
  )
}

function ProviderRow({ provider, onEdit, onToggle, onDelete, onTest }) {
  const [test, setTest] = useState(null)
  const [confirming, setConfirming] = useState(false)

  const runTest = async () => {
    setTest({ running: true })
    try {
      setTest(await onTest(provider.id))
    } catch (e) {
      setTest({ ok: false, error: e.message })
    }
  }

  return (
    <li className="border border-border rounded p-3 space-y-1" data-testid={`provider-${provider.id}`}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <span className="text-sm font-medium text-fg">{provider.name}</span>
          <span className="ml-2 text-xs text-fg-subtle font-mono">{provider.id}</span>
          {!provider.enabled && <span className="ml-2 text-xs text-fg-subtle">(disabled)</span>}
        </div>
        <div className="flex gap-1">
          <button onClick={runTest} disabled={test?.running} className={BTN}>Test</button>
          <button onClick={() => onToggle(provider)} className={BTN}>{provider.enabled ? 'Disable' : 'Enable'}</button>
          <button onClick={() => onEdit(provider)} className={BTN}>Edit</button>
          {confirming ? (
            <>
              <button onClick={() => onDelete(provider.id)} className="text-xs px-2 py-1 rounded bg-danger hover:bg-danger/80 text-white">Delete</button>
              <button onClick={() => setConfirming(false)} className={BTN}>Keep</button>
            </>
          ) : (
            <button onClick={() => setConfirming(true)} className="text-xs px-2 py-1 rounded bg-surface hover:bg-surface-strong text-danger-fg">Delete</button>
          )}
        </div>
      </div>
      <div className="text-xs text-fg-subtle font-mono break-all">{provider.base_url}</div>
      <KeyBadge provider={provider} />
      {test && !test.running && (
        <div className={`text-xs ${test.ok ? 'text-success-fg' : 'text-danger-fg'}`}>
          {test.ok ? `Connected — ${test.model_count} chat models` : `Failed: ${test.error}`}
        </div>
      )}
      {test?.running && <div className="text-xs text-fg-subtle">Testing…</div>}
    </li>
  )
}

export default function ProvidersSettings() {
  const { data, error, save, remove, test } = useProviderSettings()
  const [editing, setEditing] = useState(null)
  const [actionError, setActionError] = useState(null)

  const act = (fn) => async (...args) => {
    setActionError(null)
    try {
      await fn(...args)
    } catch (e) {
      setActionError(e.message || 'Request failed')
    }
  }

  const providers = data?.providers || []
  const ids = providers.map(p => p.id)
  const presets = (data?.presets || []).filter(p => !ids.includes(p.id))

  const handleSave = async (id, body) => {
    await save(id, body)
    setEditing(null)
  }

  return (
    <div className="bg-surface border border-border rounded-lg p-6" data-testid="providers-settings">
      <h2 className="text-lg font-medium text-fg mb-1">Model providers</h2>
      <p className="text-xs text-fg-muted mb-4">
        OpenAI-compatible APIs. All of a provider's chat models appear in the chat model pickers, on the web and on Android.
      </p>
      {error && <div className="text-xs text-danger-fg mb-3">{error}</div>}
      {actionError && <div className="text-xs text-danger-fg bg-danger-subtle border border-danger rounded px-3 py-2 mb-3">{actionError}</div>}

      {providers.length > 0 && (
        <ul className="space-y-2 mb-4">
          {providers.map(p => (
            editing && !editing.isNew && editing.initial.id === p.id ? (
              <li key={p.id}>
                <ProviderForm initial={p} isNew={false} existingIds={ids} onSave={handleSave} onCancel={() => setEditing(null)} />
              </li>
            ) : (
              <ProviderRow
                key={p.id}
                provider={p}
                onEdit={(prov) => setEditing({ initial: prov, isNew: false })}
                onToggle={act((prov) => save(prov.id, { enabled: !prov.enabled }))}
                onDelete={act(remove)}
                onTest={test}
              />
            )
          ))}
        </ul>
      )}

      {editing?.isNew ? (
        <ProviderForm initial={{}} isNew existingIds={ids} presets={presets} onSave={handleSave} onCancel={() => setEditing(null)} />
      ) : (
        <button onClick={() => setEditing({ isNew: true })} className={BTN_PRIMARY}>
          <i className="fa-solid fa-plus mr-1"></i>Add provider
        </button>
      )}
    </div>
  )
}
