import { fetchAPI } from '../api'

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
