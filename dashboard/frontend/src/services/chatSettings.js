import { fetchAPI } from '../api'

// Editable global default `main_system_prompt`. The backend returns
// { current, builtin, customized } from every verb so the UI never has to
// do its own string compare to know whether the value differs from the
// built-in baseline.
const PATH = '/chat/settings/main-system-prompt'

export const getMainSystemPrompt = () => fetchAPI(PATH)

export const putMainSystemPrompt = (content) =>
  fetchAPI(PATH, { method: 'PUT', body: JSON.stringify({ content }) })

export const resetMainSystemPrompt = () => fetchAPI(PATH, { method: 'DELETE' })
