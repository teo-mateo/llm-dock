import { useState, useEffect, useRef } from 'react'
import { fetchAPI } from '../api'

const POLL_INTERVAL = 5000

export default function useRunningServices() {
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(true)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true

    async function fetchServices() {
      try {
        const data = await fetchAPI('/services')
        if (!mountedRef.current) return
        const running = (data.services || []).filter(s =>
          s.status === 'running' && (s.name.startsWith('llamacpp-') || s.name.startsWith('vllm-'))
        )
        setServices(running)
      } catch {
        // ignore
      } finally {
        if (mountedRef.current) setLoading(false)
      }
    }

    fetchServices()
    const id = setInterval(fetchServices, POLL_INTERVAL)
    return () => {
      mountedRef.current = false
      clearInterval(id)
    }
  }, [])

  return { services, loading }
}
