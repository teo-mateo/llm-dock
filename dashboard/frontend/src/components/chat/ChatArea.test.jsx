import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import ChatArea from './ChatArea'

// useRunningServices (pulled in transitively by the empty-state composer's
// ChatInput-less path is fine, but ChatArea itself doesn't use it). We only
// exercise the no-conversation branches here, so no router/hook mocking is
// needed beyond what ChatArea's own imports require.
vi.mock('../../hooks/useRunningServices', async (importActual) => ({
  ...(await importActual()),
  default: () => ({ services: [], loading: false }),
}))

// Controllable model lists for the /model command: the SSE service list
// (unfiltered — ChatArea applies isChatService itself), the engine catalogue,
// and the configured provider groups.
const { slashState } = vi.hoisted(() => ({
  slashState: {
    services: null,
    engines: [],
    providerGroups: [],
  },
}))
vi.mock('../../hooks/useServicesSSE', () => ({
  default: () => ({ services: slashState.services, loading: false }),
}))
vi.mock('../../hooks/useEngineCatalogue', () => ({
  default: () => ({ status: 'ready', engines: slashState.engines, error: null, byType: {}, retry: () => {} }),
}))
vi.mock('../../hooks/useProviderModels', () => ({
  default: () => ({ providers: [], groups: slashState.providerGroups, loading: false, refresh: () => {} }),
}))

// Heavy children that fetch or need extra context — not under test here.
// ModelSelector captures its props so the empty-state dropdown wiring can be
// asserted without rendering the real (hook-fetching) component.
const { capturedModelSelectorProps, capturedReasoningLevelProps, capturedSamplingProps } = vi.hoisted(() => ({
  capturedModelSelectorProps: { current: null },
  capturedReasoningLevelProps: { current: null },
  capturedSamplingProps: { current: null },
}))
vi.mock('./ModelSelector', () => ({
  default: (props) => { capturedModelSelectorProps.current = props; return null },
}))
vi.mock('./ReasoningLevelSelect', () => ({
  default: (props) => {
    capturedReasoningLevelProps.current = props
    return <span data-testid="reasoning-level-slot" />
  },
}))
vi.mock('./SamplingParamsControl', () => ({
  default: (props) => {
    capturedSamplingProps.current = props
    return <span data-testid="sampling-slot" />
  },
}))
vi.mock('./McpToggle', () => ({ default: () => null }))
vi.mock('./MessageList', () => ({ default: () => null }))

vi.mock('../../hooks/useChatPrompts', () => ({
  default: () => ({
    prompts: [
      { id: 'prompt-1', name: 'Prompt 1', content: 'You are a helpful assistant.', sort_order: 0 },
      { id: 'prompt-2', name: 'Prompt 2', content: 'You are a coding expert.', sort_order: 1 },
    ],
    loading: false,
    error: null,
    refetch: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    reorder: vi.fn(),
  }),
}))

const { mockUpdateConversation } = vi.hoisted(() => ({ mockUpdateConversation: vi.fn() }))
vi.mock('../../services/chat', async (importActual) => ({
  ...(await importActual()),
  updateConversation: (...args) => mockUpdateConversation(...args),
}))

afterEach(() => cleanup())

describe('ChatArea no-conversation states', () => {
  beforeEach(() => {
    capturedModelSelectorProps.current = null
  })

  it('shows the create composer with a pre-selected model dropdown when there is no route conversation', () => {
    const { container } = render(
      <ChatArea
        conversation={null}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        selectedModel="vllm-test"
        onModelChange={() => {}}
        onCreateAndSend={() => {}}
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
      />
    )
    expect(container.textContent).toContain('Start a new conversation')
    expect(container.querySelector('textarea')).toBeTruthy()
    // Empty-state dropdown: single model select, pre-selected with the default.
    expect(capturedModelSelectorProps.current).not.toBeNull()
    expect(capturedModelSelectorProps.current.variant).toBe('new-chat')
    expect(capturedModelSelectorProps.current.mainService).toBe('vllm-test')
    expect(capturedModelSelectorProps.current.disabled).toBe(false)
  })

  it('hides the model dropdown and disables the composer when no model is available', () => {
    const { container } = render(
      <ChatArea
        conversation={null}
        awaitingConversation={false}
        defaultModelName={null}
        selectedModel={null}
        onModelChange={() => {}}
        onCreateAndSend={() => {}}
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
      />
    )
    expect(container.textContent).toContain('No model available. Start a local model or configure a provider in Settings.')
    expect(capturedModelSelectorProps.current).toBeNull()
    expect(container.querySelector('textarea').disabled).toBe(true)
  })

  it('shows a loading state (no composer) while a URL conversation is fetching', () => {
    // Opening /v2/chat/<id> directly
    // leaves `conversation` null during loadConversation — the empty-state
    // composer must NOT render, or typing would create a different chat.
    const { container } = render(
      <ChatArea
        conversation={null}
        awaitingConversation={true}
        defaultModelName="vllm-test"
        onCreateAndSend={() => {}}
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
      />
    )
    expect(container.textContent).toContain('Loading conversation')
    expect(container.textContent).not.toContain('Start a new conversation')
    expect(container.querySelector('textarea')).toBeNull()
  })

  it('shows loading (not the stale chat) when switching to a different route id', () => {
    // loadConversation does not clear
    // the previous conversation before fetching, so when switching from A
    // to B, `conversation` is still A while awaitingConversation is true.
    // awaitingConversation must be authoritative — render loading, not A's
    // composer — or an Enter would send into A via its stale closure.
    const { container } = render(
      <ChatArea
        conversation={{ id: 'conv-A', main_service: 'vllm-test' }}
        awaitingConversation={true}
        defaultModelName="vllm-test"
        onCreateAndSend={() => {}}
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
      />
    )
    expect(container.textContent).toContain('Loading conversation')
    expect(container.querySelector('textarea')).toBeNull()
  })
})

describe('ChatArea — prompt selection', () => {
  // PromptSelector is read-only (no async save), so handleSend does not
  // need to flush a pending edit before sending.
  beforeEach(() => {
    mockUpdateConversation.mockReset()
  })

  function renderConversation(onSend, { mainSystemPrompt = '', promptId = null } = {}) {
    return render(
      <ChatArea
        conversation={{
          id: 'conv-1',
          main_service: 'vllm-test',
          main_system_prompt: mainSystemPrompt,
          prompt_id: promptId,
          mcp_servers: [],
        }}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
        streaming={false}
        onSend={onSend}
      />
    )
  }

  it('shows the selected prompt name in the selector button', () => {
    renderConversation(vi.fn(), { mainSystemPrompt: 'You are a helpful assistant.', promptId: 'prompt-1' })
    expect(screen.getByText('Prompt 1')).toBeTruthy()
  })

  it('shows None for a legacy conversation whose text only matches a prompt', () => {
    // The selection is the stored reference, not a content match: a
    // pre-feature conversation with no prompt_id is custom text even when
    // it happens to equal a managed prompt's content.
    renderConversation(vi.fn(), { mainSystemPrompt: 'You are a helpful assistant.' })
    expect(screen.getByText('None')).toBeTruthy()
  })

  it('selecting a prompt calls updateConversation with the id only', () => {
    renderConversation(vi.fn())

    fireEvent.click(screen.getByRole('button', { name: /System Prompt/ }))
    fireEvent.click(screen.getByRole('radio', { name: /Prompt 1/ }))

    expect(mockUpdateConversation).toHaveBeenCalledWith('conv-1', {
      prompt_id: 'prompt-1',
    })
  })

  it('selecting None detaches the reference and clears the text', () => {
    renderConversation(vi.fn(), { mainSystemPrompt: 'You are a helpful assistant.', promptId: 'prompt-1' })

    fireEvent.click(screen.getByRole('button', { name: /System Prompt/ }))
    fireEvent.click(screen.getByRole('radio', { name: /^None/ }))

    expect(mockUpdateConversation).toHaveBeenCalledWith('conv-1', {
      prompt_id: null,
      main_system_prompt: '',
    })
  })

  it('sends a message immediately without any prompt-save flush', async () => {
    const onSend = vi.fn()
    const { container } = renderConversation(onSend)

    const composer = container.querySelector('textarea')
    fireEvent.change(composer, { target: { value: 'hello' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('hello', undefined))
  })
})

describe('ChatArea — /model slash command', () => {
  beforeEach(() => {
    mockUpdateConversation.mockReset()
    mockUpdateConversation.mockResolvedValue({ id: 'conv-1' })
    slashState.services = [
      { name: 'vllm-qwen', template_type: 'vllm', status: 'running', kind: 'chat' },
      { name: 'llamacpp-27b', template_type: 'llamacpp', status: 'exited', kind: 'chat' },
      { name: 'vllm-nomic-embed', template_type: 'vllm', status: 'running', kind: 'embedding' },
    ]
    slashState.engines = []
    slashState.providerGroups = [
      { id: 'mistral', name: 'Mistral', models: [{ id: 'mistral-large-latest', label: 'Mistral Large' }] },
    ]
  })

  const OPENROUTER_MODELS = [{ id: 'anthropic/claude-sonnet-5', label: 'Claude Sonnet 5' }]

  function renderWithConversation(onSend = vi.fn(), extra = {}) {
    const onReloadConversation = vi.fn()
    const utils = render(
      <ChatArea
        conversation={{ id: 'conv-1', main_service: 'vllm-qwen', mcp_servers: [] }}
        awaitingConversation={false}
        defaultModelName="vllm-qwen"
        openRouterModels={OPENROUTER_MODELS}
        onSend={onSend}
        onReloadConversation={onReloadConversation}
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
        {...extra}
      />
    )
    return { onSend, onReloadConversation, ...utils }
  }

  function typeCommand(container, text) {
    const composer = container.querySelector('textarea')
    fireEvent.change(composer, { target: { value: text } })
    fireEvent.keyDown(composer, { key: 'Enter' })
  }

  it('switches the main model, reloads the conversation, and never sends', async () => {
    const { onSend, onReloadConversation, container } = renderWithConversation()
    typeCommand(container, '/model llamacpp-27b')

    await waitFor(() => {
      expect(mockUpdateConversation).toHaveBeenCalledWith('conv-1', { main_service: 'llamacpp-27b' })
      expect(onReloadConversation).toHaveBeenCalledWith('conv-1')
    })
    expect(onSend).not.toHaveBeenCalled()
    expect(container.textContent).toContain('Switched main model to llamacpp-27b')
  })

  it('resolves a curated OpenRouter label to its openrouter: service string', async () => {
    const { container } = renderWithConversation()
    typeCommand(container, '/model Claude Sonnet 5')

    await waitFor(() => {
      expect(mockUpdateConversation)
        .toHaveBeenCalledWith('conv-1', { main_service: 'openrouter:anthropic/claude-sonnet-5' })
    })
  })

  it('resolves a provider service string as-is', async () => {
    const { container } = renderWithConversation()
    typeCommand(container, '/model mistral:mistral-large-latest')

    await waitFor(() => {
      expect(mockUpdateConversation)
        .toHaveBeenCalledWith('conv-1', { main_service: 'mistral:mistral-large-latest' })
    })
  })

  it('resolves an exact openrouter: string that is the current model (no-op)', async () => {
    const { container } = renderWithConversation(vi.fn(), {
      conversation: { id: 'conv-1', main_service: 'openrouter:old/model-x', mcp_servers: [] },
    })
    typeCommand(container, '/model openrouter:old/model-x')

    await waitFor(() => {
      expect(mockUpdateConversation)
        .toHaveBeenCalledWith('conv-1', { main_service: 'openrouter:old/model-x' })
    })
  })

  it('rejects an exact openrouter: string that is unoffered and not current', async () => {
    const { onSend, container } = renderWithConversation()
    typeCommand(container, '/model openrouter:old/model-x')

    await waitFor(() => {
      expect(container.textContent).toContain('Unknown model "openrouter:old/model-x"')
    })
    expect(mockUpdateConversation).not.toHaveBeenCalled()
    expect(onSend).not.toHaveBeenCalled()
  })

  it('shows an error notice when the switch fails and does not reload', async () => {
    mockUpdateConversation.mockRejectedValueOnce(new Error('boom'))
    const { onReloadConversation, container } = renderWithConversation()
    typeCommand(container, '/model llamacpp-27b')

    await waitFor(() => {
      expect(container.textContent).toContain("Couldn't switch to llamacpp-27b: boom")
    })
    expect(onReloadConversation).not.toHaveBeenCalled()
  })

  it('matches curated labels case-insensitively', async () => {
    const { container } = renderWithConversation()
    typeCommand(container, '/model claude sonnet 5')

    await waitFor(() => {
      expect(mockUpdateConversation)
        .toHaveBeenCalledWith('conv-1', { main_service: 'openrouter:anthropic/claude-sonnet-5' })
    })
  })

  it('names the candidates when a label matches several models', async () => {
    slashState.providerGroups = [
      { id: 'mistral', name: 'Mistral', models: [{ id: 'm1', label: 'Claude Sonnet 5' }] },
    ]
    const { onSend, container } = renderWithConversation()
    typeCommand(container, '/model Claude Sonnet 5')

    await waitFor(() => expect(container.textContent).toContain('matches several models'))
    expect(container.textContent).toContain('openrouter:anthropic/claude-sonnet-5')
    expect(container.textContent).toContain('mistral:m1')
    expect(mockUpdateConversation).not.toHaveBeenCalled()
    expect(onSend).not.toHaveBeenCalled()
  })

  it('shows an error notice for an unknown ref and changes nothing', async () => {
    const { onSend, container } = renderWithConversation()
    typeCommand(container, '/model nope')

    await waitFor(() => expect(container.textContent).toContain('Unknown model "nope"'))
    expect(mockUpdateConversation).not.toHaveBeenCalled()
    expect(onSend).not.toHaveBeenCalled()
  })

  it('does not offer embedding services to the command', async () => {
    const { onSend, container } = renderWithConversation()
    typeCommand(container, '/model vllm-nomic-embed')

    await waitFor(() => expect(container.textContent).toContain('Unknown model "vllm-nomic-embed"'))
    expect(mockUpdateConversation).not.toHaveBeenCalled()
    expect(onSend).not.toHaveBeenCalled()
  })

  it('bare /model lists local (with status), OpenRouter, and provider models, and sends nothing', async () => {
    const { onSend, container } = renderWithConversation()
    typeCommand(container, '/model')

    await waitFor(() => expect(container.textContent).toContain('Local models:'))
    expect(container.textContent).toContain('vllm-qwen (running)')
    expect(container.textContent).toContain('llamacpp-27b (stopped)')
    expect(container.textContent).toContain('openrouter:anthropic/claude-sonnet-5')
    expect(container.textContent).toContain('mistral:mistral-large-latest')
    expect(container.textContent).not.toContain('vllm-nomic-embed')
    expect(mockUpdateConversation).not.toHaveBeenCalled()
    expect(onSend).not.toHaveBeenCalled()
  })

  it('keeps the bare-/model list until it is dismissed', async () => {
    const { container } = renderWithConversation()
    typeCommand(container, '/model')
    await waitFor(() => expect(container.textContent).toContain('Local models:'))

    fireEvent.click(container.querySelector('button[aria-label="Dismiss model notice"]'))
    await waitFor(() => expect(container.textContent).not.toContain('Local models:'))
  })

  it('clears the list notice on the next send', async () => {
    const { onSend, container } = renderWithConversation()
    typeCommand(container, '/model')
    await waitFor(() => expect(container.textContent).toContain('Local models:'))

    const composer = container.querySelector('textarea')
    fireEvent.change(composer, { target: { value: 'hello' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('hello', undefined))
    expect(container.textContent).not.toContain('Local models:')
  })

  it('passes non-command text through to the normal send', async () => {
    const { onSend, container } = renderWithConversation()
    typeCommand(container, 'hello /model vllm-qwen')

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('hello /model vllm-qwen', undefined))
    expect(mockUpdateConversation).not.toHaveBeenCalled()
  })

  it('passes multi-line input through to the normal send', async () => {
    const { onSend, container } = renderWithConversation()
    typeCommand(container, '/model vllm-qwen\nsecond line')

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('/model vllm-qwen\nsecond line', undefined))
    expect(mockUpdateConversation).not.toHaveBeenCalled()
  })

  it('passes /modelx through to the normal send', async () => {
    const { onSend, container } = renderWithConversation()
    typeCommand(container, '/modelx vllm-qwen')

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('/modelx vllm-qwen', undefined))
    expect(mockUpdateConversation).not.toHaveBeenCalled()
  })

  it('passes a command typed with an image through to the normal send', async () => {
    const { onSend, container } = renderWithConversation()
    const fileInput = container.querySelector('input[type="file"]')
    fireEvent.change(fileInput, {
      target: { files: [new File(['img'], 'pic.png', { type: 'image/png' })] },
    })
    await waitFor(() => expect(container.querySelector('img[alt="pic.png"]')).toBeTruthy())

    typeCommand(container, '/model vllm-qwen')

    await waitFor(() => expect(onSend).toHaveBeenCalled())
    expect(onSend.mock.calls[0][0]).toBe('/model vllm-qwen')
    expect(Array.isArray(onSend.mock.calls[0][1])).toBe(true)
    expect(onSend.mock.calls[0][1]).toHaveLength(1)
    expect(mockUpdateConversation).not.toHaveBeenCalled()
  })

  describe('empty-state composer', () => {
    function renderEmpty(onModelChange, onCreateAndSend) {
      return render(
        <ChatArea
          conversation={null}
          awaitingConversation={false}
          defaultModelName="vllm-qwen"
          selectedModel="vllm-qwen"
          openRouterModels={OPENROUTER_MODELS}
          onModelChange={onModelChange}
          onCreateAndSend={onCreateAndSend}
          messages={[]}
          critiques={{}}
          setCritiques={() => {}}
        />
      )
    }

    it('pre-selects the model without creating a conversation or sending', async () => {
      const onModelChange = vi.fn()
      const onCreateAndSend = vi.fn()
      const { container } = renderEmpty(onModelChange, onCreateAndSend)
      typeCommand(container, '/model llamacpp-27b')

      await waitFor(() => expect(onModelChange).toHaveBeenCalledWith('llamacpp-27b'))
      expect(onCreateAndSend).not.toHaveBeenCalled()
      expect(mockUpdateConversation).not.toHaveBeenCalled()
      expect(container.textContent).toContain('New conversations will start on llamacpp-27b')
    })

    it('resolves curated OpenRouter refs the same way in the empty state', async () => {
      const onModelChange = vi.fn()
      const onCreateAndSend = vi.fn()
      const { container } = renderEmpty(onModelChange, onCreateAndSend)
      typeCommand(container, '/model Claude Sonnet 5')

      await waitFor(() => {
        expect(onModelChange).toHaveBeenCalledWith('openrouter:anthropic/claude-sonnet-5')
      })
      expect(onCreateAndSend).not.toHaveBeenCalled()
    })

    it('passes normal text through to create-and-send', async () => {
      const onModelChange = vi.fn()
      const onCreateAndSend = vi.fn()
      const { container } = renderEmpty(onModelChange, onCreateAndSend)
      typeCommand(container, 'hello')

      await waitFor(() => expect(onCreateAndSend).toHaveBeenCalledWith('hello', undefined))
      expect(onModelChange).not.toHaveBeenCalled()
    })
  })
})

describe('ChatArea — active background run on return', () => {
  // Returning to a conversation whose run
  // is still going (streaming false, but conversation.active_run set) must keep
  // the composer blocked and offer Stop — otherwise the run is uncontrollable
  // and a send just hits the backend 409 active-run guard.
  function renderWith(activeRun, onStopStreaming = () => {}) {
    return render(
      <ChatArea
        conversation={{
          id: 'conv-1',
          main_service: 'vllm-test',
          main_system_prompt: '',
          mcp_servers: [],
          active_run: activeRun,
        }}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
        streaming={false}
        onStopStreaming={onStopStreaming}
      />
    )
  }

  it('disables the composer and shows Stop for a running active_run with no local stream', () => {
    const onStop = vi.fn()
    const { container } = renderWith({ status: 'running' }, onStop)
    expect(container.querySelector('textarea').disabled).toBe(true)
    const stop = screen.getByRole('button', { name: /Stop/ })
    fireEvent.click(stop)
    expect(onStop).toHaveBeenCalledTimes(1)
  })

  it('also blocks for a queued active_run', () => {
    const { container } = renderWith({ status: 'queued' })
    expect(container.querySelector('textarea').disabled).toBe(true)
    expect(screen.getByRole('button', { name: /Stop/ })).toBeTruthy()
  })

  it('enables the composer and hides Stop when there is no active run', () => {
    const { container } = renderWith(null)
    expect(container.querySelector('textarea').disabled).toBe(false)
    expect(screen.queryByRole('button', { name: /Stop/ })).toBeNull()
  })

  it('does not block for a terminal active_run', () => {
    const { container } = renderWith({ status: 'completed' })
    expect(container.querySelector('textarea').disabled).toBe(false)
    expect(screen.queryByRole('button', { name: /Stop/ })).toBeNull()
  })
})

describe('ChatArea — Stop gating on runReady', () => {
  // While streaming but before run_started has
  // delivered the run id (runReady false), Stop must be hidden so the UI can't
  // issue an unguarded cancel. Once runReady is true, Stop appears.
  function renderStreaming(runReady) {
    return render(
      <ChatArea
        conversation={{ id: 'conv-1', main_service: 'vllm-test', main_system_prompt: '', mcp_servers: [], active_run: null }}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
        streaming={true}
        runReady={runReady}
        onStopStreaming={() => {}}
      />
    )
  }

  it('hides Stop while streaming until the run id is known', () => {
    renderStreaming(false)
    expect(screen.queryByRole('button', { name: /Stop/ })).toBeNull()
  })

  it('shows Stop once runReady is true', () => {
    renderStreaming(true)
    expect(screen.getByRole('button', { name: /Stop/ })).toBeTruthy()
  })
})

describe('ChatArea — reasoning level', () => {
  beforeEach(() => {
    capturedReasoningLevelProps.current = null
    mockUpdateConversation.mockReset()
  })

  function renderConversationExtra(conversation, onReloadConversation, extra = {}) {
    return render(
      <ChatArea
        conversation={conversation}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
        streaming={false}
        onSend={() => {}}
        onReloadConversation={onReloadConversation}
        {...extra}
      />
    )
  }

  // A dropped level is invisible in the answer, so the run_started note shows.
  it('shows the server note about a level this run ignored', () => {
    renderConversationExtra({
      id: 'conv-1', main_service: 'llamacpp-x', main_system_prompt: '',
      mcp_servers: [], reasoning_level: 'low',
    }, undefined, { runNotice: "Reasoning level 'low' is not offered by this model and was ignored" })
    expect(screen.getByText(/is not offered by this model and was ignored/)).toBeTruthy()
  })

  it('shows no note for a run that dropped nothing', () => {
    renderConversationExtra({
      id: 'conv-1', main_service: 'llamacpp-x', main_system_prompt: '',
      mcp_servers: [], reasoning_level: 'low',
    })
    expect(screen.queryByText(/not offered by this model/)).toBeNull()
  })

  it('shows the picker with the conversation and its stored level', () => {
    renderConversationExtra({
      id: 'conv-1', main_service: 'llamacpp-x', main_system_prompt: '',
      mcp_servers: [], reasoning_level: 'low',
    })
    const props = capturedReasoningLevelProps.current
    expect(props).not.toBeNull()
    expect(props.mainService).toBe('llamacpp-x')
    expect(props.value).toBe('low')
    // A live run must not be interruptible by a level change.
    expect(props.disabled).toBe(false)
  })

  it('lives in the composer, not the conversation header', () => {
    renderConversationExtra({
      id: 'conv-1', main_service: 'llamacpp-x', main_system_prompt: '',
      mcp_servers: [], reasoning_level: 'low',
    })
    const slot = screen.getByTestId('reasoning-level-slot')
    const form = document.querySelector('textarea').closest('form')
    // Placement, not existence: the header's model picker sits outside the form.
    expect(form.contains(slot)).toBe(true)
    // Shares the composer row with the attach button, which proves placement.
    expect(form.contains(screen.getByLabelText('Attach files'))).toBe(true)
  })

  it('keeps the conversation viewer in the header, out of the composer', () => {
    renderConversationExtra({
      id: 'conv-1', main_service: 'llamacpp-x', main_system_prompt: '',
      mcp_servers: [], reasoning_level: null,
    })
    const viewer = screen.getByLabelText('Open conversation viewer')
    // It inspects the conversation, not the draft: with it in the composer it
    // was the only labelled control in the row and out-signalled send.
    expect(viewer.closest('form')).toBeNull()
    expect(document.querySelector('textarea').closest('form').contains(viewer)).toBe(false)
  })

  it('saves a changed level on the conversation and reloads it', async () => {
    const onReload = vi.fn()
    mockUpdateConversation.mockResolvedValue({})
    renderConversationExtra({
      id: 'conv-1', main_service: 'llamacpp-x', main_system_prompt: '',
      mcp_servers: [], reasoning_level: 'low',
    }, onReload)
    capturedReasoningLevelProps.current.onChange('medium')
    await waitFor(() => expect(mockUpdateConversation).toHaveBeenCalledWith(
      'conv-1', { reasoning_level: 'medium' }))
    await waitFor(() => expect(onReload).toHaveBeenCalledWith('conv-1'))
  })

  it('passes null straight through when the level is cleared', async () => {
    mockUpdateConversation.mockResolvedValue({})
    renderConversationExtra({
      id: 'conv-1', main_service: 'llamacpp-x', main_system_prompt: '',
      mcp_servers: [], reasoning_level: 'medium',
    })
    capturedReasoningLevelProps.current.onChange(null)
    await waitFor(() => expect(mockUpdateConversation).toHaveBeenCalledWith(
      'conv-1', { reasoning_level: null }))
  })

  it('shows the sampling control with the conversation and its stored set', () => {
    renderConversationExtra({
      id: 'conv-1', main_service: 'vllm-x', main_system_prompt: '',
      mcp_servers: [], sampling_params: { temperature: 0.4, seed: 9 },
    })
    const props = capturedSamplingProps.current
    expect(props).not.toBeNull()
    expect(props.mainService).toBe('vllm-x')
    expect(props.value).toEqual({ temperature: 0.4, seed: 9 })
    expect(props.disabled).toBe(false)
  })

  it('mounts the sampling control in the composer, not the header', () => {
    renderConversationExtra({
      id: 'conv-1', main_service: 'vllm-x', main_system_prompt: '',
      mcp_servers: [], sampling_params: null,
    })
    const form = document.querySelector('textarea').closest('form')
    expect(form.contains(screen.getByTestId('sampling-slot'))).toBe(true)
  })

  it('saves the set the control returns and reloads the conversation', async () => {
    const onReload = vi.fn()
    mockUpdateConversation.mockResolvedValue({})
    renderConversationExtra({
      id: 'conv-1', main_service: 'vllm-x', main_system_prompt: '',
      mcp_servers: [], sampling_params: { temperature: 0.4 },
    }, onReload)
    capturedSamplingProps.current.onChange({ top_k: 20 })
    await waitFor(() => expect(mockUpdateConversation).toHaveBeenCalledWith(
      'conv-1', { sampling_params: { top_k: 20 } }))
    await waitFor(() => expect(onReload).toHaveBeenCalledWith('conv-1'))
  })

  it('passes null straight through when the sampling set is cleared', async () => {
    mockUpdateConversation.mockResolvedValue({})
    renderConversationExtra({
      id: 'conv-1', main_service: 'vllm-x', main_system_prompt: '',
      mcp_servers: [], sampling_params: { temperature: 0.4 },
    })
    capturedSamplingProps.current.onChange(null)
    await waitFor(() => expect(mockUpdateConversation).toHaveBeenCalledWith(
      'conv-1', { sampling_params: null }))
  })

  it('disables the picker while a run is active', () => {
    render(
      <ChatArea
        conversation={{
          id: 'conv-1', main_service: 'llamacpp-x', main_system_prompt: '',
          mcp_servers: [], reasoning_level: null,
        }}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
        streaming={true}
        runReady={true}
        onStopStreaming={() => {}}
      />
    )
    expect(capturedReasoningLevelProps.current.disabled).toBe(true)
  })

  it('offers pre-selection in the new-chat composer', () => {
    const onReasoningLevelChange = vi.fn()
    render(
      <ChatArea
        conversation={null}
        awaitingConversation={false}
        defaultModelName="vllm-test"
        selectedModel="llamacpp-x"
        onModelChange={() => {}}
        selectedReasoningLevel="off"
        onReasoningLevelChange={onReasoningLevelChange}
        onCreateAndSend={() => {}}
        messages={[]}
        critiques={{}}
        setCritiques={() => {}}
      />
    )
    const props = capturedReasoningLevelProps.current
    expect(props.mainService).toBe('llamacpp-x')
    expect(props.value).toBe('off')
    props.onChange('xhigh')
    expect(onReasoningLevelChange).toHaveBeenCalledWith('xhigh')
  })
})
