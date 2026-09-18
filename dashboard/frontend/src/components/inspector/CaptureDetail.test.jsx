import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import CaptureDetail from './CaptureDetail'

function detail(overrides = {}) {
  const request = {
    model: 'qwen3.8-27b',
    stream: true,
    temperature: 0.7,
    messages: [
      { role: 'system', content: 'You are helpful.' },
      { role: 'user', content: 'hello' },
    ],
    tools: [
      { type: 'function', function: { name: 'get_weather', description: 'Weather lookup', parameters: { type: 'object' } } },
      { type: 'function', function: { name: 'search', description: 'Web search', parameters: { type: 'object' } } },
    ],
  }
  return {
    id: 'c1',
    service_name: 'llamacpp-qwen3',
    model: 'qwen3.8-27b',
    template_type: 'llamacpp',
    method: 'POST',
    path: '/v1/chat/completions',
    status_code: 200,
    stream: true,
    request_headers: { Authorization: '***redacted***', 'Content-Type': 'application/json' },
    request_body: JSON.stringify(request),
    response_body: 'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n',
    response_text: '# hi',
    reasoning_text: 'thinking hard',
    tool_calls: [{ id: 'r1', function: { name: 'reply', arguments: '{"text":"hi"}' } }],
    finish_reason: 'stop',
    prompt_tokens: 10,
    completion_tokens: 3,
    total_tokens: 13,
    ttfb_ms: 412,
    duration_ms: 8391,
    error: null,
    request_truncated: false,
    response_truncated: false,
    created_at: '2026-09-18T20:14:03.412Z',
    ...overrides,
  }
}

function setup(capture = detail(), props = {}) {
  const onDelete = vi.fn()
  const onConfirmStateChange = vi.fn()
  const view = render(
    <CaptureDetail
      capture={capture}
      onDelete={onDelete}
      onConfirmStateChange={onConfirmStateChange}
      {...props}
    />
  )
  return { view, onDelete, onConfirmStateChange }
}

function openTab(name) {
  fireEvent.click(screen.getByRole('button', { name }))
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('CaptureDetail header', () => {
  it('shows the model, the meta line and both action buttons', () => {
    setup()
    expect(screen.getByText('qwen3.8-27b')).toBeInTheDocument()
    expect(screen.getByText(/llamacpp-qwen3 · POST \/v1\/chat\/completions/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Copy request JSON/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Delete$/ })).toBeInTheDocument()
  })

  it('Delete asks inline and only then calls onDelete', () => {
    const { onDelete, onConfirmStateChange } = setup()
    fireEvent.click(screen.getByRole('button', { name: /^Delete$/ }))
    expect(onConfirmStateChange).toHaveBeenLastCalledWith(true)
    expect(onDelete).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onDelete).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: /^Delete$/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete?' }))
    expect(onDelete).toHaveBeenCalledWith('c1')
  })

  it('Copy request JSON copies the verbatim body', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    setup()

    fireEvent.click(screen.getByRole('button', { name: /Copy request JSON/ }))
    await vi.waitFor(() => expect(writeText).toHaveBeenCalled())
    expect(writeText.mock.calls[0][0]).toContain('"messages"')
  })
})

describe('CaptureDetail tabs', () => {
  it('renders the five tabs in order with the Tools count badge', () => {
    setup()
    const tabs = ['Conversation', 'Tools', 'Request', 'Response', 'Meta']
    const buttons = screen.getAllByRole('button', { name: (n) => tabs.some((t) => n === t || n.startsWith(t)) })
    const labels = buttons.map((b) => b.textContent.replace(/\d+$/, ''))
    expect(labels.slice(0, 5)).toEqual(tabs)
    expect(screen.getByRole('button', { name: /^Tools/ }).textContent).toContain('2')
  })

  it('defaults to Conversation showing the message cards', () => {
    setup()
    expect(screen.getByText('You are helpful.')).toBeInTheDocument()
    expect(screen.getByText('2 messages · 2 tools · 21 chars')).toBeInTheDocument()
  })

  it('falls back to the no-messages copy with a working raw-request link', () => {
    setup(detail({ request_body: '{ not json' }))
    expect(screen.getByText('This request has no message array.')).toBeInTheDocument()
    openTab(/^View raw request$/)
    expect(screen.getByText(/Request body is not JSON/)).toBeInTheDocument()
  })

  it('Tools tab lists definitions and collapses them all', () => {
    setup()
    openTab(/^Tools/)
    expect(screen.getByText('get_weather')).toBeInTheDocument()
    expect(screen.getByText('Weather lookup')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Collapse all' }))
    const open = document.querySelectorAll('details[open]')
    expect(open.length).toBe(0)
    fireEvent.click(screen.getByRole('button', { name: 'Expand all' }))
    expect(document.querySelectorAll('details[open]').length).toBe(2)
  })

  it('Tools tab shows the empty state when no tools were sent', () => {
    const request = { model: 'm', messages: [{ role: 'user', content: 'x' }] }
    setup(detail({ request_body: JSON.stringify(request) }))
    openTab(/^Tools/)
    expect(screen.getByText('No tools were sent with this request.')).toBeInTheDocument()
  })

  it('Request tab lists non-message fields, the raw body and a truncation banner', () => {
    setup(detail({ request_truncated: true }))
    openTab(/^Request/)
    expect(screen.getByText('Request body was truncated at 1 MB.')).toBeInTheDocument()
    expect(screen.getByText('temperature')).toBeInTheDocument()
    expect(screen.getByText('0.7')).toBeInTheDocument()
    expect(screen.getByText('model')).toBeInTheDocument()
    expect(screen.queryByText('messages')).not.toBeInTheDocument()
    expect(screen.getByText(/"messages"/)).toBeInTheDocument()
  })

  it('Response tab shows Thinking collapsed, rendered text, tool calls and raw SSE', () => {
    setup()
    openTab(/^Response/)
    const thinking = [...document.querySelectorAll('summary')].find((s) => s.textContent.includes('Thinking'))
    expect(thinking).toBeInTheDocument()
    expect(thinking.parentElement.hasAttribute('open')).toBe(false)

    expect(screen.getByRole('heading', { name: 'hi', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('stop')).toBeInTheDocument()
    expect(screen.getByText('reply')).toBeInTheDocument()

    const raw = [...document.querySelectorAll('summary')].find((s) => s.textContent.includes('Raw response'))
    expect(raw.parentElement.hasAttribute('open')).toBe(false)
    fireEvent.click(raw)
    expect(screen.getByText(/data: \[DONE\]/)).toBeInTheDocument()
  })

  it('Response tab truncation banner mirrors the request banner', () => {
    setup(detail({ response_truncated: true }))
    openTab(/^Response/)
    expect(screen.getByText('Response body was truncated at 1 MB.')).toBeInTheDocument()
  })

  it('Meta tab renders the definition list and the redacted headers', () => {
    setup()
    openTab(/^Meta/)
    expect(screen.getByText('Template type')).toBeInTheDocument()
    expect(screen.getAllByText('llamacpp').length).toBeGreaterThan(0)
    expect(screen.getByText('***redacted***')).toBeInTheDocument()
    expect(screen.getByText('Authorization')).toBeInTheDocument()
  })
})
