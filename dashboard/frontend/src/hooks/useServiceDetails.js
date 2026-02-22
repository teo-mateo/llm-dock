import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchAPI } from '../api'
import { startService, stopService, restartService } from '../services/lifecycle'

const POLL_INTERVAL = 3000

export default function useServiceDetails(serviceName) {
  const [config, setConfig] = useState(null)
  const [runtime, setRuntime] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [transitioning, setTransitioning] = useState(null)
  const mountedRef = useRef(true)

  const fetchConfig = useCallback(async () => {
    try {
      const data = await fetchAPI(`/services/${serviceName}`)
      if (mountedRef.current) {
        setConfig(data.config)
      }
    } catch (err) {
      if (mountedRef.current) {
        if (err.message.includes('404') || err.message.includes('not found')) {
          setError('not-found')
        } else {
          setError(err.message)
        }
      }
    }
  }, [serviceName])

  const fetchRuntime = useCallback(async () => {
    try {
      const data = await fetchAPI('/services')
      if (mountedRef.current) {
        const svc = (data.services || []).find(s => s.name === serviceName)
        if (svc) {
          setRuntime(svc)
          setError(null)
        } else {
          // Don't set 'not-found' here — the list endpoint may be transiently
          // incomplete during compose reloads. fetchConfig hitting the
          // per-service endpoint is the authoritative existence check.
          setRuntime(null)
        }
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message)
      }
    }
  }, [serviceName])

  // Initial fetch: config + runtime in parallel
  useEffect(() => {
    mountedRef.current = true
    setLoading(true)
    setError(null)

    Promise.all([fetchConfig(), fetchRuntime()]).then(() => {
      if (mountedRef.current) setLoading(false)
    })

    return () => { mountedRef.current = false }
  }, [fetchConfig, fetchRuntime])

  // Poll runtime every 3s
  useEffect(() => {
    if (loading || error === 'not-found') return

    const id = setInterval(fetchRuntime, POLL_INTERVAL)
    return () => clearInterval(id)
  }, [loading, error, fetchRuntime])

  const refetchConfig = useCallback(async () => {
    await fetchConfig()
  }, [fetchConfig])

  // Lifecycle actions
  const start = useCallback(async () => {
    setTransitioning('starting')
    try {
      await startService(serviceName)
      await fetchRuntime()
    } finally {
      if (mountedRef.current) setTransitioning(null)
    }
  }, [serviceName, fetchRuntime])

  const stop = useCallback(async () => {
    setTransitioning('stopping')
    try {
      await stopService(serviceName)
      await fetchRuntime()
    } finally {
      if (mountedRef.current) setTransitioning(null)
    }
  }, [serviceName, fetchRuntime])

  const restart = useCallback(async () => {
    setTransitioning('restarting')
    try {
      await restartService(serviceName)
      await fetchRuntime()
    } finally {
      if (mountedRef.current) setTransitioning(null)
    }
  }, [serviceName, fetchRuntime])

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
    await fetchRuntime()
    await fetchConfig()
    return data
  }, [serviceName, fetchRuntime, fetchConfig])

  const fetchYamlPreview = useCallback(async () => {
    const data = await fetchAPI(`/services/${serviceName}/preview`)
    return data.yaml
  }, [serviceName])

  const registerOpenWebUI = useCallback(async () => {
    const data = await fetchAPI(`/services/${serviceName}/register-openwebui`, { method: 'POST' })
    await fetchRuntime()
    return data
  }, [serviceName, fetchRuntime])

  const unregisterOpenWebUI = useCallback(async () => {
    const data = await fetchAPI(`/services/${serviceName}/unregister-openwebui`, { method: 'POST' })
    await fetchRuntime()
    return data
  }, [serviceName, fetchRuntime])

  return {
    config, runtime, loading, error, transitioning,
    refetchConfig,
    actions: { start, stop, restart, rename, deleteService, setPublicPort, fetchYamlPreview, registerOpenWebUI, unregisterOpenWebUI },
  }
}
