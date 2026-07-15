import { fetchAPI, API_BASE, getToken } from '../api'

export async function createConversation(data) {
  return fetchAPI('/chat/conversations', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function listConversations(limit = 50, offset = 0) {
  return fetchAPI(`/chat/conversations?limit=${limit}&offset=${offset}`)
}

export async function getConversation(id) {
  return fetchAPI(`/chat/conversations/${id}`)
}

export async function updateConversation(id, data) {
  return fetchAPI(`/chat/conversations/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteConversation(id) {
  return fetchAPI(`/chat/conversations/${id}`, {
    method: 'DELETE',
  })
}

export async function deleteConversations(ids) {
  return fetchAPI('/chat/conversations/delete', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  })
}

// -- Projects --

export async function listProjects() {
  return fetchAPI('/chat/projects')
}

export async function createProject(data) {
  return fetchAPI('/chat/projects', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateProject(id, data) {
  return fetchAPI(`/chat/projects/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteProject(id) {
  return fetchAPI(`/chat/projects/${id}`, {
    method: 'DELETE',
  })
}

// -- Project files --

export async function getProjectFilesTree(projectId) {
  return fetchAPI(`/chat/projects/${projectId}/files`)
}

// Multipart upload — bypasses fetchAPI because Content-Type must be set by
// the browser (multipart boundary), not forced to application/json.
export async function uploadProjectFile(projectId, file, { dir = '', overwrite = false } = {}) {
  const token = getToken()
  if (!token) throw new Error('Not authenticated')
  const form = new FormData()
  form.append('file', file)
  form.append('dir', dir)
  if (overwrite) form.append('overwrite', 'true')
  const response = await fetch(`${API_BASE}/chat/projects/${projectId}/files/upload`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: form,
  })
  if (!response.ok) {
    let msg = `HTTP ${response.status}`
    try { msg = (await response.json()).error || msg } catch { /* not JSON */ }
    throw new Error(msg)
  }
  return response.json()
}

export async function mkdirProjectPath(projectId, path) {
  return fetchAPI(`/chat/projects/${projectId}/files/mkdir`, {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
}

export async function moveProjectPath(projectId, path, newPath) {
  return fetchAPI(`/chat/projects/${projectId}/files/move`, {
    method: 'POST',
    body: JSON.stringify({ path, new_path: newPath }),
  })
}

export async function deleteProjectPath(projectId, path) {
  return fetchAPI(`/chat/projects/${projectId}/files?path=${encodeURIComponent(path)}`, {
    method: 'DELETE',
  })
}

export async function getProjectFileContent(projectId, path) {
  return fetchAPI(`/chat/projects/${projectId}/files/content?path=${encodeURIComponent(path)}`)
}

export async function saveProjectFileContent(projectId, path, content, baseModifiedAt = null) {
  const body = { path, content }
  if (baseModifiedAt != null) body.base_modified_at = baseModifiedAt
  return fetchAPI(`/chat/projects/${projectId}/files/content`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

// Fetches the file with auth and hands back a blob URL the caller must
// revoke after use (a plain <a href> can't carry the bearer token).
export async function downloadProjectFile(projectId, path) {
  const token = getToken()
  if (!token) throw new Error('Not authenticated')
  const response = await fetch(
    `${API_BASE}/chat/projects/${projectId}/files/download?path=${encodeURIComponent(path)}`,
    { headers: { 'Authorization': `Bearer ${token}` } },
  )
  if (!response.ok) {
    let msg = `HTTP ${response.status}`
    try { msg = (await response.json()).error || msg } catch { /* not JSON */ }
    throw new Error(msg)
  }
  return URL.createObjectURL(await response.blob())
}

export async function requestCritique(messageId, { contextWindow = 10, extraInstructions = '' } = {}) {
  return fetchAPI(`/chat/messages/${messageId}/critique`, {
    method: 'POST',
    body: JSON.stringify({ context_window: contextWindow, extra_instructions: extraInstructions }),
  })
}

export async function getCritique(messageId) {
  return fetchAPI(`/chat/messages/${messageId}/critique`)
}

// -- Runs (background-run observation + cancellation, issue #58) --

export async function getRun(runId) {
  return fetchAPI(`/chat/runs/${runId}`)
}

export async function cancelRun(runId) {
  return fetchAPI(`/chat/runs/${runId}/cancel`, {
    method: 'POST',
  })
}

// Cancel a conversation's active run by conversation id. The Stop button uses
// this so cancellation never depends on having captured the run id from the
// run_started frame — the server can always find the run from the conversation.
// expectedRunId, when known, is sent as a guard so a late-arriving cancel can't
// kill a newer run that started after the one the user actually stopped.
export async function cancelActiveRun(conversationId, expectedRunId = null) {
  return fetchAPI(`/chat/conversations/${conversationId}/cancel-active-run`, {
    method: 'POST',
    body: JSON.stringify(expectedRunId ? { expected_run_id: expectedRunId } : {}),
  })
}
