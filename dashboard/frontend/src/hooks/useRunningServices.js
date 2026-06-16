import { useMemo } from 'react'
import useServicesSSE from './useServicesSSE'

/**
 * Hook for getting running inference services (llama.cpp and vLLM only).
 * Derives state from the SSE stream via useServicesSSE.
 *
 * By default returns only chat-capable services — embedding pooling
 * services (vLLM `--runner pooling` / `--convert embed`, llama.cpp
 * `--embedding`) can't serve `/v1/chat/completions` and shouldn't appear
 * in the chat composer's default-model slot. Pass `kind: 'all'` for the
 * Services dashboard which needs every running container.
 */
export default function useRunningServices({ kind = 'chat' } = {}) {
  const { services, loading } = useServicesSSE()

  const runningServices = useMemo(() => {
    if (!services) return []
    return services.filter(s => {
      if (s.status !== 'running') return false
      if (!s.name.startsWith('llamacpp-') && !s.name.startsWith('vllm-') && !s.name.startsWith('ds4-')) return false
      if (kind === 'all') return true
      // Snapshot pre-rollout: treat missing kind as 'chat' so old payloads
      // don't filter everything out.
      return (s.kind || 'chat') === kind
    })
  }, [services, kind])

  return { services: runningServices, loading }
}
