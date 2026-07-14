import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ChatPage from './ChatPage'

// This file covers the default-model fallback: with zero local services
// running, a configured OpenRouter model must make chat creation possible
// (ChatArea gets a non-null defaultModelName), and with neither source the
// composer stays disabled (null).

vi.mock('./ChatSidebar', () => ({ default: () => null }))

const { capturedAreaProps } = vi.hoisted(() => ({ capturedAreaProps: { current: null } }))
vi.mock('./ChatArea', () => ({
  default: (props) => { capturedAreaProps.current = props; return null },
}))

const { mockServicesSSE, mockOpenRouterModels } = vi.hoisted(() => ({
  mockServicesSSE: vi.fn(),
  mockOpenRouterModels: vi.fn(),
}))
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
  mockListConversations.mockReset()
  mockListConversations.mockResolvedValue({ conversations: [] })
})

afterEach(() => cleanup())

describe('ChatPage default model fallback', () => {
  it('prefers the first running local service', async () => {
    mockServicesSSE.mockReturnValue({ services: [{ name: 'vllm-test', status: 'running', kind: 'chat' }], loading: false })
    mockOpenRouterModels.mockReturnValue({
      data: { configured: true, current: [{ id: 'vendor/model-a', label: 'Model A' }], builtin: [], customized: false },
      loading: false,
    })
    renderPage()
    await waitFor(() => expect(capturedAreaProps.current).not.toBeNull())
    expect(capturedAreaProps.current.defaultModelName).toBe('vllm-test')
  })

  it('falls back to the first OpenRouter model when no local service runs', async () => {
    mockServicesSSE.mockReturnValue({ services: [], loading: false })
    mockOpenRouterModels.mockReturnValue({
      data: { configured: true, current: [{ id: 'vendor/model-a', label: 'Model A' }], builtin: [], customized: false },
      loading: false,
    })
    renderPage()
    await waitFor(() => expect(capturedAreaProps.current).not.toBeNull())
    // Displayed via formatModelLabel — the friendly curated label.
    expect(capturedAreaProps.current.defaultModelName).toBe('Model A · OpenRouter')
  })

  it('passes null when neither local services nor OpenRouter are available', async () => {
    mockServicesSSE.mockReturnValue({ services: [], loading: false })
    mockOpenRouterModels.mockReturnValue({
      data: { configured: false, current: [{ id: 'vendor/model-a', label: 'Model A' }], builtin: [], customized: false },
      loading: false,
    })
    renderPage()
    await waitFor(() => expect(capturedAreaProps.current).not.toBeNull())
    expect(capturedAreaProps.current.defaultModelName).toBe(null)
  })
})
