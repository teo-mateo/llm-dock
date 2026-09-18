import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { fetchAPI, setServiceInspect } from '../api'

function Switch({ checked, disabled, label, onClick }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface ${checked ? 'bg-accent' : 'bg-surface-strong'} ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-6' : 'translate-x-1'}`} />
    </button>
  )
}

function ProxyState({ info }) {
  const running = info?.proxy_running
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`inline-block w-2.5 h-2.5 rounded-full ${running ? 'bg-success' : 'bg-danger'}`} />
      <span className={running ? 'text-success-fg' : 'text-danger-fg'}>{running ? 'Running' : 'Not running'}</span>
    </span>
  )
}

export default function InspectToggleCard({ config, runtime, serviceName, onSaved, onError }) {
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [inspectInfo, setInspectInfo] = useState(null)
  const mountedRef = useRef(true)

  const inspectOn = !!config?.inspect
  const upstreamPort = config?.inspect_upstream_port
  const hostPort = runtime?.host_port ?? config?.port
  const isRunning = runtime?.status === 'running'
  const target = !inspectOn

  // Captures count and live proxy state. A failed read only hides the
  // Captures row — it must not break the card.
  const loadInspectInfo = useCallback(async () => {
    try {
      const data = await fetchAPI('/inspector/services')
      if (!mountedRef.current) return
      const row = (data.services || []).find(s => s.service_name === serviceName)
      setInspectInfo(row || null)
    } catch {
      // keep whatever the last toggle response said
    }
  }, [serviceName])

  useEffect(() => {
    mountedRef.current = true
    loadInspectInfo()
    return () => { mountedRef.current = false }
  }, [loadInspectInfo])

  const runToggle = useCallback(async (enabled) => {
    setBusy(true)
    try {
      const res = await setServiceInspect(serviceName, enabled)
      // The response is authoritative for the proxy state right after the
      // toggle; the re-fetch reconciles the capture count.
      setInspectInfo({
        proxy_running: res.proxy_running,
        error: res.error,
        listen_port: res.port,
        upstream_port: res.upstream_port,
        capture_count: null,
      })
      loadInspectInfo()
      const suffix = res.restarted ? ' (container restarted)' : ''
      const message = enabled
        ? `Inspection enabled — clients keep using port ${res.port}${suffix}`
        : `Inspection disabled${suffix}`
      onSaved(message)
    } catch (err) {
      // No optimistic state: the card only flips on the response, so a
      // failed request leaves the switch exactly where it was.
      onError(err.message)
    } finally {
      setBusy(false)
      setConfirming(false)
    }
  }, [serviceName, loadInspectInfo, onSaved, onError])

  const handleToggleClick = () => {
    if (busy || confirming) return
    if (isRunning) {
      setConfirming(true)
      return
    }
    runToggle(target)
  }

  const bannerVisible = inspectOn && inspectInfo && !inspectInfo.proxy_running && inspectInfo.error
  const showCaptures = inspectInfo && inspectInfo.capture_count != null

  return (
    <div className="bg-surface rounded-lg border border-border p-5" aria-busy={busy}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <i className="fa-solid fa-magnifying-glass text-fg-muted"></i>
          <h2 className="text-base font-semibold text-fg">Request inspection</h2>
        </div>

        {busy ? (
          <div className="flex items-center gap-2 text-sm text-fg-muted">
            <i className="fa-solid fa-spinner fa-spin"></i>
            <span>{target ? 'Enabling…' : 'Disabling…'}</span>
          </div>
        ) : confirming ? (
          <div className="flex items-center gap-3 text-sm">
            <span className="text-fg-muted">Recreate {serviceName} now?</span>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="px-3 py-1.5 rounded border border-border text-fg-muted hover:text-fg cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => runToggle(target)}
              className="px-3 py-1.5 rounded bg-accent-strong text-white font-medium cursor-pointer"
            >
              {inspectOn ? 'Disable' : 'Enable'}
            </button>
          </div>
        ) : (
          <Switch
            checked={inspectOn}
            disabled={busy}
            label={`Toggle request inspection for ${serviceName}`}
            onClick={handleToggleClick}
          />
        )}
      </div>

      {isRunning && (
        <p className="mt-3 text-sm text-danger-fg">
          <i className="fa-solid fa-triangle-exclamation mr-2"></i>
          Toggling recreates the container. In-flight requests will fail.
        </p>
      )}

      {bannerVisible && (
        <div className="mt-3 rounded border border-danger bg-danger-subtle px-3 py-2 text-sm text-danger-fg flex items-center justify-between gap-3">
          <span>Proxy failed to bind port {inspectInfo.listen_port ?? hostPort}: {inspectInfo.error}</span>
          <button
            type="button"
            onClick={() => runToggle(true)}
            className="shrink-0 px-3 py-1 rounded bg-danger text-white font-medium cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {inspectOn ? (
        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <dt className="text-fg-subtle text-xs uppercase tracking-wide">Client port</dt>
          <dd className="text-fg">
            {hostPort}
            <span className="ml-2 text-fg-subtle text-xs">clients keep this URL</span>
          </dd>

          <dt className="text-fg-subtle text-xs uppercase tracking-wide">Container port</dt>
          <dd className="text-fg font-mono">
            127.0.0.1:{upstreamPort}
            <span className="ml-2 font-sans text-fg-subtle text-xs">loopback only</span>
          </dd>

          <dt className="text-fg-subtle text-xs uppercase tracking-wide">Proxy</dt>
          <dd><ProxyState info={inspectInfo} /></dd>

          {showCaptures && (
            <>
              <dt className="text-fg-subtle text-xs uppercase tracking-wide">Captures</dt>
              <dd className="text-fg">
                {inspectInfo.capture_count} recorded
                <Link
                  to={`/inspector?service=${encodeURIComponent(serviceName)}`}
                  className="ml-2 text-accent-fg hover:text-accent-fg-hover hover:underline"
                >
                  View in Inspector
                </Link>
              </dd>
            </>
          )}
        </dl>
      ) : (
        <p className="mt-4 text-sm text-fg-muted">
          Off — requests go straight to the container. Turn this on to record every payload sent
          to this model: system prompt, messages, tool definitions and the response.
        </p>
      )}

      <p className="mt-4 text-xs text-fg-subtle">
        Captures every client that reaches this port — llm-dock chat, the Android client, <code className="font-mono">curl</code>.
      </p>
    </div>
  )
}
