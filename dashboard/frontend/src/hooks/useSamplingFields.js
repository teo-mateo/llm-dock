import { useCallback, useEffect, useRef, useState } from 'react'
import { getSamplingFields } from '../services/samplingFields'

// One entry per service name, shared by every mount: the answer is per-engine
// static data, and the composer can mount two of these at once (new-chat and
// conversation). Bounded by the number of services on the host, so no eviction.
const cache = new Map()

export function invalidateSamplingFields(service) {
  if (service === undefined) cache.clear()
  else cache.delete(service)
}

/**
 * The sampling fields one service accepts: { engine, fields, loading, error, refresh }.
 *
 * `fields` is empty for an engine with no verified mapping — including every
 * service name the dashboard does not know, which is the same answer the runner
 * gives when it decides what to send.
 */
export default function useSamplingFields(service) {
  const cached = service ? cache.get(service) : null
  const [state, setState] = useState(() => (
    cached
      ? { engine: cached.engine, fields: cached.fields, loading: false, error: null }
      : { engine: null, fields: [], loading: !!service, error: null }
  ))
  const mounted = useRef(true)

  const load = useCallback(async (force = false) => {
    if (!service) {
      setState({ engine: null, fields: [], loading: false, error: null })
      return
    }
    if (!force && cache.has(service)) {
      const hit = cache.get(service)
      setState({ engine: hit.engine, fields: hit.fields, loading: false, error: null })
      return
    }
    setState(prev => ({ ...prev, loading: true }))
    try {
      const data = await getSamplingFields(service)
      const next = { engine: data.engine || null, fields: data.fields || [], loading: false, error: null }
      cache.set(service, next)
      if (mounted.current) setState(next)
    } catch (e) {
      // A service that is not running is still a service: the endpoint answers for
      // it. A failure here is the dashboard being unreachable, so say so rather
      // than rendering an empty control that looks like "no knobs".
      if (mounted.current) {
        setState({ engine: null, fields: [], loading: false, error: e.message || 'Could not load sampling fields' })
      }
    }
  }, [service])

  useEffect(() => {
    mounted.current = true
    // set-state-in-effect: fetch on mount / service change, cached per service in `cache`.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
    return () => { mounted.current = false }
  }, [load])

  const refresh = useCallback(() => load(true), [load])

  return { ...state, refresh }
}
