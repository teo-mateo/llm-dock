import { fetchAPI } from '../api'

export async function startService(name) {
  await fetchAPI(`/services/${name}/start`, { method: 'POST' })
}

export async function stopService(name) {
  await fetchAPI(`/services/${name}/stop`, { method: 'POST' })
}

export async function restartService(name) {
  try {
    await fetchAPI(`/services/${name}/stop`, { method: 'POST' })
  } catch { /* continue to start */ }
  await fetchAPI(`/services/${name}/start`, { method: 'POST' })
}
