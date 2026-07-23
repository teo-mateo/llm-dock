import { fetchAPI } from '../api'

const PATH = '/chat/prompts'

export async function fetchPrompts() {
  const data = await fetchAPI(PATH)
  return data.prompts || []
}

export async function createPrompt(name, content) {
  return fetchAPI(PATH, {
    method: 'POST',
    body: JSON.stringify({ name, content }),
  })
}

export async function updatePrompt(id, name, content) {
  return fetchAPI(`${PATH}/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ name, content }),
  })
}

export async function deletePrompt(id) {
  return fetchAPI(`${PATH}/${id}`, {
    method: 'DELETE',
  })
}

export async function reorderPrompts(ids) {
  return fetchAPI(`${PATH}/reorder`, {
    method: 'PATCH',
    body: JSON.stringify({ ids }),
  })
}
