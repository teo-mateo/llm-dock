import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import GhostChatPage from './GhostChatPage'

const { mockSendMessage, mockStopStreaming, hookState } = vi.hoisted(() => ({
  mockSendMessage: vi.fn(),
  mockStopStreaming: vi.fn(),
  hookState: {
    messages: [
      { id: 'g1', role: 'user', content: 'sensitive question', images: [], tool_calls: null, reasoning_content: null },
    ],
    streaming: true,
    streamingContent: 'thinking…',
    streamingReasoning: '',
    toolEvents: [],
    streamingArtifacts: [],
    error: null,
  },
}))
vi.mock('../../hooks/useGhostChat', () => ({
  default: () => ({ ...hookState, sendMessage: mockSendMessage, stopStreaming: mockStopStreaming }),
}))

function resetHookState() {
  Object.assign(hookState, {
    messages: [
      { id: 'g1', role: 'user', content: 'sensitive question', images: [], tool_calls: null, reasoning_content: null },
    ],
    streaming: true,
    streamingContent: 'thinking…',
    streamingReasoning: '',
    toolEvents: [],
    streamingArtifacts: [],
    error: null,
  })
}

vi.mock('./ModelSelector', () => ({
  default: ({ mainService, onChangeMain }) => (
    <select
      data-testid="ghost-model"
      value={mainService}
      onChange={e => onChangeMain(e.target.value)}
    >
      <option value="">no model</option>
      <option value="vllm-a">vllm-a</option>
    </select>
  ),
}))

vi.mock('./McpToggle', () => ({
  default: ({ enabledServers, onChange }) => (
    <button
      data-testid="ghost-mcp"
      onClick={() => onChange(enabledServers.includes('sympy-math') ? [] : ['sympy-math'])}
    >
      {enabledServers.join(',') || 'mcp-off'}
    </button>
  ),
}))

vi.mock('./MessageList', () => ({
  default: ({ messages, streaming, streamingContent }) => (
    <div data-testid="ghost-messages">
      {messages.map(m => <div key={m.id} data-testid={`msg-${m.id}`}>{m.content}</div>)}
      {streaming && <div data-testid="ghost-streaming">{streamingContent}</div>}
    </div>
  ),
}))

vi.mock('./ChatInput', () => ({
  default: ({ onSend, disabled }) => (
    <div>
      <button data-testid="ghost-send" onClick={() => onSend('hello', [])} disabled={disabled}>send</button>
      <span data-testid="ghost-disabled">{String(disabled)}</span>
    </div>
  ),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  resetHookState()
})

describe('GhostChatPage', () => {
  it('shows the ephemeral banner and the in-flight turn', () => {
    render(<GhostChatPage />)
    expect(screen.getByText(/Ghost mode — nothing is saved/)).toBeTruthy()
    expect(screen.getByTestId('msg-g1')).toHaveTextContent('sensitive question')
    expect(screen.getByTestId('ghost-streaming')).toHaveTextContent('thinking…')
  })

  it('disables sending until a model is chosen', () => {
    resetHookState()
    hookState.streaming = false
    render(<GhostChatPage />)
    expect(screen.getByTestId('ghost-disabled')).toHaveTextContent('true')
    fireEvent.change(screen.getByTestId('ghost-model'), { target: { value: 'vllm-a' } })
    expect(screen.getByTestId('ghost-disabled')).toHaveTextContent('false')
  })

  it('sends through the ghost hook with the selected model and mcp servers', () => {
    resetHookState()
    hookState.streaming = false
    render(<GhostChatPage />)
    fireEvent.change(screen.getByTestId('ghost-model'), { target: { value: 'vllm-a' } })
    fireEvent.click(screen.getByTestId('ghost-mcp'))
    fireEvent.click(screen.getByTestId('ghost-send'))

    expect(mockSendMessage).toHaveBeenCalledWith('hello', [], {
      serviceName: 'vllm-a',
      mcpServers: ['sympy-math'],
    })
  })

  it('offers Stop while streaming and calls stopStreaming', () => {
    render(<GhostChatPage />)
    fireEvent.click(screen.getByRole('button', { name: /Stop/i }))
    expect(mockStopStreaming).toHaveBeenCalled()
  })
})
