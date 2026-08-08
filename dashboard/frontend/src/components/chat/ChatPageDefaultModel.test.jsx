import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ChatPage from './ChatPage'

// This file covers the default-model fallback: with zero local services
// running, a configured OpenRouter model must make chat creation possible
// (ChatArea gets a non-null defaultModelName, pre-selected as selectedModel),
// and with neither source the composer stays disabled (null).

vi.mock('./ChatSidebar', () => ({ default: () => null }))

const { capturedAreaProps } = vi.hoisted(() => ({ capturedAreaProps: { current: null } }))
vi.mock('./ChatArea', () => ({
  default: (props) => { capturedAreaProps.current = props; return null },
}))

const { mockServicesSSE, mockOpenRouterModels, servicesRef } = vi.hoisted(() => ({
  mockServicesSSE: vi.fn(),
  mockOpenRouterModels: vi.fn(),
  servicesRef: { current: [] },
}))
// The SSE mock reads from a mutable ref so a mid-test services change can be
// observed after a forced re-render (see the "keeps a user-chosen model" test).
mockServicesSSE.mockImplementation(() => ({ services: servicesRef.current, loading: false }))
vi.mock('../../hooks/useServicesSSE', () => ({ default: (...a) => mockServicesSSE(...a) }))
vi.mock('../../hooks/useOpenRouterModels', () => ({ default: (...a) => mockOpenRouterModels(...a) }))

const { mockListConversations } = vi.hoisted(() => ({ mockListConversations: vi.fn() }))
vi.mock('../../services/chat', async (importActual) => ({
  ...(await importActual()),
  listConversations: (...a) => mockListConversations(...a),
}))

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/chat']}>
      <Routes>
        <Route path="/chat/:conversationId?" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  capturedAreaProps.current = null
  servicesRef.current = []
  mockListConversations.mockReset()
  mockListConversations.mockResolvedValue({ conversations: [] })
})

afterEach(() => cleanup())

describe('ChatPage default model fallback', () => {
  it('prefers the first running local service', async () => {
    servicesRef.current = [{ name: 'vllm-test', status: 'running', kind: 'chat' }]
    mockOpenRouterModels.mockReturnValue({
      data: { configured: true, current: [{ id: 'vendor/model-a', label: 'Model A' }], builtin: [], customized: false },
      loading: false,
    })
    renderPage()
    await waitFor(() => expect(capturedAreaProps.current).not.toBeNull())
    expect(capturedAreaProps.current.defaultModelName).toBe('vllm-test')
    // Pre-selected in the empty-state dropdown.
    expect(capturedAreaProps.current.selectedModel).toBe('vllm-test')
  })

  it('falls back to the first OpenRouter model when no local service runs', async () => {
    servicesRef.current = []
    mockOpenRouterModels.mockReturnValue({
      data: { configured: true, current: [{ id: 'vendor/model-a', label: 'Model A' }], builtin: [], customized: false },
      loading: false,
    })
    renderPage()
    await waitFor(() => expect(capturedAreaProps.current).not.toBeNull())
    // Raw service name — the empty-state dropdown displays the curated label.
    expect(capturedAreaProps.current.defaultModelName).toBe('openrouter:vendor/model-a')
    expect(capturedAreaProps.current.selectedModel).toBe('openrouter:vendor/model-a')
  })

  it('passes null when neither local services nor OpenRouter are available', async () => {
    servicesRef.current = []
    mockOpenRouterModels.mockReturnValue({
      data: { configured: false, current: [{ id: 'vendor/model-a', label: 'Model A' }], builtin: [], customized: false },
      loading: false,
    })
    renderPage()
    await waitFor(() => expect(capturedAreaProps.current).not.toBeNull())
    expect(capturedAreaProps.current.defaultModelName).toBe(null)
    expect(capturedAreaProps.current.selectedModel).toBe(null)
  })

  it('keeps a user-chosen model when the default changes', async () => {
    servicesRef.current = [{ name: 'vllm-test', status: 'running', kind: 'chat' }]
    mockOpenRouterModels.mockReturnValue({
      data: { configured: true, current: [{ id: 'vendor/model-a', label: 'Model A' }], builtin: [], customized: false },
      loading: false,
    })
    const { rerender } = renderPage()
    await waitFor(() => expect(capturedAreaProps.current).not.toBeNull())
    // User picks a different model in the empty-state dropdown.
    capturedAreaProps.current.onModelChange('vllm-other')
    await waitFor(() => expect(capturedAreaProps.current.selectedModel).toBe('vllm-other'))
    // The default changes (a new service starts) — the user's choice wins.
    servicesRef.current = [{ name: 'vllm-new', status: 'running', kind: 'chat' }]
    rerender(
      <MemoryRouter initialEntries={['/chat']}>
        <Routes>
          <Route path="/chat/:conversationId?" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>
    )
    await waitFor(() => expect(capturedAreaProps.current.defaultModelName).toBe('vllm-new'))
    expect(capturedAreaProps.current.selectedModel).toBe('vllm-other')
  })
})
