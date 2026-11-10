import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchAPI } from '../api'

let loaded = null
let inflight = null

export function resetEngineCatalogue() {
  loaded = null
  inflight = null
}

function load() {
  if (loaded) return Promise.resolve(loaded)
  if (!inflight) {
    inflight = fetchAPI('/engines')
      .then(data => {
        loaded = data.engines || []
        return loaded
      })
      .finally(() => { inflight = null })
  }
  return inflight
}

const LOADING = { status: 'loading', engines: [], error: null }

export default function useEngineCatalogue() {
  const [state, setState] = useState(() => (
    loaded ? { status: 'ready', engines: loaded, error: null } : LOADING
  ))
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    load().then(
      engines => { if (!cancelled) setState({ status: 'ready', engines, error: null }) },
      err => { if (!cancelled) setState({ status: 'error', engines: [], error: err.message }) },
    )
    return () => { cancelled = true }
  }, [attempt])

  const retry = useCallback(() => {
    setState(LOADING)
    setAttempt(n => n + 1)
  }, [])

  const byType = useMemo(
    () => Object.fromEntries(state.engines.map(engine => [engine.type, engine])),
    [state.engines],
  )

  return { ...state, byType, retry }
}
