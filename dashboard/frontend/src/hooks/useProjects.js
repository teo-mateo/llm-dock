import { useState, useEffect, useCallback, useRef } from 'react'
import { listProjects, createProject, updateProject, deleteProject } from '../services/chat'

export default function useProjects() {
  const [projects, setProjects] = useState([])
  const mountedRef = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const data = await listProjects()
      if (mountedRef.current) {
        setProjects(data.projects || [])
      }
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    // set-state-in-effect: fetch on mount (refresh is a stable useCallback([])).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh()
    return () => { mountedRef.current = false }
  }, [refresh])

  const create = useCallback(async (data) => {
    const project = await createProject(data)
    await refresh()
    return project
  }, [refresh])

  const rename = useCallback(async (id, name) => {
    await updateProject(id, { name })
    await refresh()
  }, [refresh])

  const remove = useCallback(async (id) => {
    await deleteProject(id)
    await refresh()
  }, [refresh])

  return { projects, refresh, create, rename, remove }
}
