import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { fetchAPI } from '../api'
import { startService, stopService, restartService } from '../services/lifecycle'
import useServicesSSE from './useServicesSSE'

export default function useServiceDetails(serviceName) {
  const [config, setConfig] = useState(null)
  const [configError, setConfigError] = useState(null)
  const [configLoading, setConfigLoading] = useState(true)
  const [transitioning, setTransitioning] = useState(null)
  const mountedRef = useRef(true)

  // Runtime state (status, container_id, host_port, etc.) comes from the
  // shared SSE stream. No polling here; lifecycle actions don't need to
  // call back to refresh because the Docker event manager pushes a delta
  // within ~1s of the container state change.
  const { services, loading: sseLoading, error: sseError } = useServicesSSE()
  const runtime = useMemo(() => {
    if (!services) return null
    return services.find(s => s.name === serviceName) || null
  }, [services, serviceName])

  const fetchConfig = useCallback(async () => {
    try {
      const data = await fetchAPI(`/services/${serviceName}`)
      if (mountedRef.current) {
        setConfig(data.config)
        setConfigError(null)
      }
    } catch (err) {
      if (mountedRef.current) {
        if (err.message.includes('404') || err.message.includes('not found')) {
          setConfigError('not-found')
        } else {
          setConfigError(err.message)
        }
      }
    }
  }, [serviceName])

  // Initial config fetch (and refetch when serviceName changes)
  useEffect(() => {
    mountedRef.current = true
    setConfigLoading(true)
    setConfigError(null)
    fetchConfig().finally(() => {
      if (mountedRef.current) setConfigLoading(false)
    })
    return () => { mountedRef.current = false }
  }, [fetchConfig])

  // 'not-found' from the config endpoint is authoritative — it's the only
  // surface that distinguishes "deleted" from "transiently absent from the
  // list during compose reloads". SSE errors are surfaced as a secondary
  // signal (connection problems), and the SSE snapshot may take a tick
  // longer than the config call to arrive.
  const error = configError === 'not-found' ? 'not-found' : (configError || sseError)
  const loading = configLoading || sseLoading

  const refetchConfig = useCallback(async () => {
    await fetchConfig()
  }, [fetchConfig])

  // Lifecycle actions. No manual runtime refresh — the SSE stream will
  // deliver the new status as soon as docker emits the event.
  const start = useCallback(async () => {
    setTransitioning('starting')
    try {
      await startService(serviceName)
    } finally {
      if (mountedRef.current) setTransitioning(null)
    }
  }, [serviceName])

  const stop = useCallback(async () => {
    setTransitioning('stopping')
    try {
      await stopService(serviceName)
    } finally {
      if (mountedRef.current) setTransitioning(null)
    }
  }, [serviceName])

  const restart = useCallback(async () => {
    setTransitioning('restarting')
    try {
      await restartService(serviceName)
    } finally {
      if (mountedRef.current) setTransitioning(null)
    }
  }, [serviceName])

  const rename = useCallback(async (newName) => {
    await fetchAPI(`/services/${serviceName}/rename`, {
      method: 'POST',
      body: JSON.stringify({ new_name: newName }),
    })
  }, [serviceName])

  const deleteService = useCallback(async () => {
    await fetchAPI(`/services/${serviceName}`, { method: 'DELETE' })
  }, [serviceName])

  const setPublicPort = useCallback(async () => {
    const data = await fetchAPI(`/services/${serviceName}/set-public-port`, { method: 'POST' })
    // set-public-port changes the host port, which is part of the config
    // (services.json) — runtime status is unaffected, but config needs a
    // refresh because the change isn't on the SSE feed.
    await fetchConfig()
    return data
  }, [serviceName, fetchConfig])

  const fetchYamlPreview = useCallback(async () => {
    const data = await fetchAPI(`/services/${serviceName}/preview`)
    return data.yaml
  }, [serviceName])

  const registerOpenWebUI = useCallback(async () => {
    const data = await fetchAPI(`/services/${serviceName}/register-openwebui`, { method: 'POST' })
    return data
  }, [serviceName])

  const unregisterOpenWebUI = useCallback(async () => {
    const data = await fetchAPI(`/services/${serviceName}/unregister-openwebui`, { method: 'POST' })
    return data
  }, [serviceName])

  return {
    config, runtime, loading, error, transitioning,
    refetchConfig,
    actions: { start, stop, restart, rename, deleteService, setPublicPort, fetchYamlPreview, registerOpenWebUI, unregisterOpenWebUI },
  }
}
