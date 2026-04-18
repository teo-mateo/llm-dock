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

export async function requestCritique(messageId, { contextWindow = 10, extraInstructions = '' } = {}) {
  return fetchAPI(`/chat/messages/${messageId}/critique`, {
    method: 'POST',
    body: JSON.stringify({ context_window: contextWindow, extra_instructions: extraInstructions }),
  })
}

export async function getCritique(messageId) {
  return fetchAPI(`/chat/messages/${messageId}/critique`)
}
