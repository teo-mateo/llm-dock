import { API_BASE, fetchAPI, getToken, handleAuthFailure } from '../api'
import { createSseParser } from '../utils/sseFrames'

export async function readPiStream(path, { signal, lastEventId, onFrame } = {}) {
  const token = getToken()
  if (!token) {
    handleAuthFailure()
    const error = new Error('Not authenticated')
    error.status = 401
    throw error
  }

  const headers = { Authorization: `Bearer ${token}` }
  if (lastEventId) headers['Last-Event-ID'] = String(lastEventId)

  const response = await fetch(`${API_BASE}${path}`, { headers, signal })
  if (response.status === 401) {
    handleAuthFailure()
    const error = new Error('Authentication failed')
    error.status = 401
    throw error
  }
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`)
    error.status = response.status
    throw error
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const parser = createSseParser()

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
      let data
      try {
        data = JSON.parse(frame.data)
      } catch {
        continue
      }
      onFrame?.({ ...frame, data })
    }
  }
}

export const piSessionKey = (s) => `${s.session_id}/${s.instance_id}`


async function postPiCommand(path, body) {
  try {
    const data = await fetchAPI(path, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    return { status: data?.pending ? 202 : 200, body: data }
  } catch (err) {
    if (typeof err.status === 'number') {
      return { status: err.status, body: err.body ?? null }
    }
    throw err
  }
}

export async function sendPiMessage(sessionId, instanceId, text) {
  return postPiCommand(
    `/pi/sessions/${sessionId}/${instanceId}/messages`,
    { text },
  )
}

export async function abortPiRun(sessionId, instanceId) {
  return postPiCommand(
    `/pi/sessions/${sessionId}/${instanceId}/abort`,
    {},
  )
}

export async function answerPiPrompt(sessionId, instanceId, promptId, value) {
  return postPiCommand(
    `/pi/sessions/${sessionId}/${instanceId}/prompts/${encodeURIComponent(promptId)}/answer`,
    { value },
  )
}
