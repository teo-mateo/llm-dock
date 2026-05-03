import { useMemo } from 'react'
import useServicesSSE from './useServicesSSE'

/**
 * Hook for getting running inference services (llama.cpp and vLLM only).
 * Derives state from the SSE stream via useServicesSSE.
 * 
 * @returns {{
 *   services: Array<Object>,
 *   loading: boolean
 * }} Hook return value with running services and loading state
 */
export default function useRunningServices() {
  const { services, loading } = useServicesSSE()

  const runningServices = useMemo(() => {
    if (!services) return []
    // Filter to only inference services (llama.cpp and vLLM), excluding infrastructure like open-webui
    return services.filter(s =>
      s.status === 'running' && (s.name.startsWith('llamacpp-') || s.name.startsWith('vllm-'))
    )
  }, [services])

  return { services: runningServices, loading }
}
