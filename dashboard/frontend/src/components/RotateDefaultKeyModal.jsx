import { useState, useEffect, useCallback } from 'react'
import { fetchAPI } from '../api'

function KeyCopy({ value }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="flex items-center gap-2 bg-app border border-border rounded px-3 py-2">
      <code className="text-success-fg text-xs break-all flex-1">{value}</code>
      <button
        onClick={() => {
          navigator.clipboard.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }}
        className="text-fg-muted hover:text-fg text-lg leading-none cursor-pointer shrink-0"
        title="Copy"
      >
        {copied ? '✓' : '⧉'}
      </button>
    </div>
  )
}

function ServiceList({ names }) {
  return (
    <ul className="mt-1.5 max-h-40 overflow-auto text-xs font-mono text-fg-muted space-y-0.5 pl-1">
      {names.map(n => <li key={n}>• {n}</li>)}
    </ul>
  )
}

export default function RotateDefaultKeyModal({ onClose, onDone }) {
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState(null)
  const [rotating, setRotating] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetchAPI('/default-api-key/rotation-preview')
      .then(d => { if (!cancelled) setPreview(d) })
      .catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [])

  const handleRotate = useCallback(async () => {
    setRotating(true)
    setError(null)
    try {
      const d = await fetchAPI('/default-api-key/rotate', { method: 'POST' })
      setResult(d)
      onDone?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setRotating(false)
    }
  }, [onDone])

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-surface rounded-lg border border-border max-w-xl w-full max-h-[85vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-border flex justify-between items-center">
          <h3 className="text-lg font-semibold text-fg">
            {result
              ? (result.success === false
                  ? 'Default API Key Rotated — Action Required'
                  : 'Default API Key Rotated')
              : 'Rotate Default API Key'}
          </h3>
          <button onClick={onClose} className="text-fg-muted hover:text-fg cursor-pointer" aria-label="Close">✕</button>
        </div>

        <div className="px-5 py-4 overflow-auto space-y-4 text-sm text-fg-muted">
          {error && (
            <div className="bg-danger-subtle border border-danger text-danger-fg rounded px-3 py-2">{error}</div>
          )}

          {/* Result view */}
          {result && (
            <>
              <p>{result.message}</p>
              <div>
                <p className="text-fg-muted mb-1">New default API key (shared by all services):</p>
                <KeyCopy value={result.new_api_key} />
              </div>
              {result.stopped?.length > 0 && (
                <div>
                  <p className="text-fg-muted">Stopped containers (restart them when ready):</p>
                  <ServiceList names={result.stopped} />
                </div>
              )}
              {Object.keys(result.stop_errors || {}).length > 0 && (
                <div className="bg-danger-subtle border border-danger text-danger-fg rounded px-3 py-2">
                  <p>Some containers failed to stop:</p>
                  <ul className="mt-1 text-xs font-mono space-y-0.5">
                    {Object.entries(result.stop_errors).map(([n, e]) => <li key={n}>• {n}: {e}</li>)}
                  </ul>
                </div>
              )}
              {result.openwebui_registered?.length > 0 && (
                <div className="bg-warning-subtle border border-warning text-warning-fg rounded px-3 py-2">
                  <p className="font-medium">⚠ Open WebUI still holds the old key</p>
                  <p className="mt-1 text-xs">
                    Open WebUI keeps its own copy of each connection's API key. Update it in
                    {' '}<span className="font-mono">Admin → Settings → Connections</span> for these registered services:
                  </p>
                  <ServiceList names={result.openwebui_registered} />
                </div>
              )}
            </>
          )}

          {/* Confirmation view */}
          {!result && !preview && !error && (
            <p className="text-fg-subtle">Loading impact…</p>
          )}

          {!result && preview && (
            <>
              <p>
                This generates a new shared API key, writes it to
                {' '}<span className="font-mono">.env</span> and applies it to all
                {' '}<span className="font-semibold text-fg">{preview.total_services}</span> service(s)
                in <span className="font-mono">services.json</span> and the compose file.
              </p>

              {preview.running.length > 0 ? (
                <div className="bg-danger-subtle border border-danger text-danger-fg rounded px-3 py-2">
                  <p className="font-medium">⚠ {preview.running.length} running model(s) will be STOPPED</p>
                  <p className="mt-1 text-xs">They keep serving the revoked key until stopped. Restart them manually afterwards.</p>
                  <ServiceList names={preview.running} />
                </div>
              ) : (
                <p className="text-fg-subtle text-xs">No running models — nothing will be stopped.</p>
              )}

              {preview.openwebui_registered.length > 0 && (
                <div className="bg-warning-subtle border border-warning text-warning-fg rounded px-3 py-2">
                  <p className="font-medium">⚠ Open WebUI needs a manual update</p>
                  <p className="mt-1 text-xs">
                    These services are registered in Open WebUI, which stores its own copy of the key.
                    After rotation they will fail in Open WebUI until you re-enter the new key under
                    {' '}<span className="font-mono">Admin → Settings → Connections</span>:
                  </p>
                  <ServiceList names={preview.openwebui_registered} />
                </div>
              )}
            </>
          )}
        </div>

        <div className="px-5 py-4 border-t border-border flex justify-end gap-3">
          {result ? (
            <button onClick={onClose} className="px-4 py-2 bg-surface-strong hover:bg-surface-muted text-fg text-sm rounded transition-colors cursor-pointer">
              Done
            </button>
          ) : (
            <>
              <button onClick={onClose} disabled={rotating} className="px-4 py-2 bg-surface-strong hover:bg-surface-muted text-fg text-sm rounded transition-colors disabled:opacity-50 cursor-pointer">
                Cancel
              </button>
              <button
                onClick={handleRotate}
                disabled={rotating || !preview}
                className="px-4 py-2 bg-danger hover:bg-danger text-white text-sm rounded transition-colors disabled:opacity-50 cursor-pointer"
              >
                {rotating ? 'Rotating…' : 'Rotate key'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
