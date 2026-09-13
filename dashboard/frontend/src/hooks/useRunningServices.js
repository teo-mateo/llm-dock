import { useMemo } from 'react'
import useServicesSSE from './useServicesSSE'

/**
 * Hook for getting running inference services (llama.cpp and vLLM only).
 * Derives state from the SSE stream via useServicesSSE.
 *
 * Returns only chat-capable services — embedding pooling services
 * (vLLM `--runner pooling` / `--convert embed`, llama.cpp `--embedding`)
 * can't serve `/v1/chat/completions` and shouldn't appear in the chat
 * composer's default-model slot.
 */
export default function useRunningServices() {
  const { services, loading } = useServicesSSE()

  const runningServices = useMemo(() => {
    if (!services) return []
    return services.filter(s => {
      if (s.status !== 'running') return false
      if (!s.name.startsWith('llamacpp-') && !s.name.startsWith('ik-') && !s.name.startsWith('vllm-') && !s.name.startsWith('ds4-') && !s.name.startsWith('exl3-') && !s.name.startsWith('PAIR_')) return false
      // Snapshot pre-rollout: treat missing kind as 'chat' so old payloads
      // don't filter everything out.
      return (s.kind || 'chat') === 'chat'
    })
  }, [services])

  return { services: runningServices, loading }
}
