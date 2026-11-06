import { useMemo } from 'react'
import useServicesSSE from './useServicesSSE'

const CHAT_ENGINES = new Set(['llamacpp', 'ik_llamacpp', 'vllm', 'ds4', 'tabbyapi', 'ninfer', 'sglang', 'maya'])
const CHAT_PREFIXES = ['llamacpp-', 'ik-', 'vllm-', 'ds4-', 'exl3-', 'sglang-', 'ninfer-', 'maya-', 'PAIR_']

export function isChatService(s) {
  const known = CHAT_ENGINES.has(s.template_type) || CHAT_PREFIXES.some(p => s.name.startsWith(p))
  return known && (s.kind || 'chat') === 'chat'
}

export default function useRunningServices() {
  const { services, loading } = useServicesSSE()

  const runningServices = useMemo(() => {
    if (!services) return []
    return services.filter(s => s.status === 'running' && isChatService(s))
  }, [services])

  return { services: runningServices, loading }
}
