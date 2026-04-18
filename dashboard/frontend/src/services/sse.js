import { getToken } from '../api'

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? `${window.location.protocol}//${window.location.hostname}:3399/api`
  : `${window.location.protocol}//${window.location.hostname}/api`

/**
 * Stream a chat completion via SSE.
 * Uses fetch + ReadableStream because EventSource doesn't support auth headers.
 */
export async function streamChat(url, body, { onDelta, onDone, onError, onMessageSaved, onToolCall, onToolResult, onArtifact, signal, method = 'POST' }) {
  const token = getToken()
  if (!token) throw new Error('Not authenticated')

  const response = await fetch(`${API_BASE}${url}`, {
    method,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
    signal,
  })

  if (!response.ok) {
    const text = await response.text()
    let msg = `HTTP ${response.status}`
    try {
      const data = JSON.parse(text)
      msg = data.error || msg
    } catch { /* not JSON */ }
    onError?.(msg)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6)

        if (data === '[DONE]') {
          onDone?.()
          continue
        }

        try {
          const parsed = JSON.parse(data)

          // Custom events from backend
          if (parsed.type === 'message_saved') {
            onMessageSaved?.(parsed)
            continue
          }
          if (parsed.type === 'tool_call') {
            onToolCall?.(parsed)
            continue
          }
          if (parsed.type === 'tool_result') {
            onToolResult?.(parsed)
            continue
          }
          if (parsed.type === 'artifact') {
            onArtifact?.(parsed)
            continue
          }

          // Error from backend
          if (parsed.error) {
            onError?.(parsed.error)
            return
          }

          // Normal delta
          const delta = parsed.choices?.[0]?.delta
          if (delta) {
            onDelta?.({
              content: delta.content || '',
              reasoning_content: delta.reasoning_content || '',
            })
          }
        } catch {
          // Ignore unparseable lines
        }
      }
    }
  } catch (err) {
    if (err.name !== 'AbortError') {
      onError?.(err.message)
    }
  }
}
