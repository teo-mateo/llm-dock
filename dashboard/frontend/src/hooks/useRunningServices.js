import { useMemo } from 'react'
import useServicesSSE from './useServicesSSE'
import useEngineCatalogue from './useEngineCatalogue'

const PAIR_PREFIX = 'PAIR_'

// A model service carries a template_type in the payload; a delta stub that
// has not been through a snapshot yet is recognised by its engine's name
// prefix, which the engine catalogue supplies.
export function isChatService(s, engines = []) {
  const prefixes = engines.map(engine => `${engine.name_prefix}-`)
  const known = Boolean(s.template_type)
    || s.name.startsWith(PAIR_PREFIX)
    || prefixes.some(p => s.name.startsWith(p))
  return known && (s.kind || 'chat') === 'chat'
}

export default function useRunningServices() {
  const { services, loading } = useServicesSSE()
  const { engines } = useEngineCatalogue()

  const runningServices = useMemo(() => {
    if (!services) return []
    return services.filter(s => s.status === 'running' && isChatService(s, engines))
  }, [services, engines])

  return { services: runningServices, loading }
}
