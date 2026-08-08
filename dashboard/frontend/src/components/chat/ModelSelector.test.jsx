import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, fireEvent, cleanup } from '@testing-library/react'
import ModelSelector from './ModelSelector'

const { mockRunningServices, mockOpenRouterModels } = vi.hoisted(() => ({
  mockRunningServices: vi.fn(),
  mockOpenRouterModels: vi.fn(),
}))
vi.mock('../../hooks/useRunningServices', () => ({ default: (...a) => mockRunningServices(...a) }))
vi.mock('../../hooks/useOpenRouterModels', () => ({ default: (...a) => mockOpenRouterModels(...a) }))

const LOCAL = [{ name: 'vllm-test' }]
const CURATED = [{ id: 'vendor/model-a', label: 'Model A' }]

function setup({ services = LOCAL, configured = true, current = CURATED, mainService = '' } = {}) {
  mockRunningServices.mockReturnValue({ services, loading: false })
  mockOpenRouterModels.mockReturnValue({
    data: { configured, current, builtin: CURATED, customized: false },
    loading: false,
  })
  return render(
    <ModelSelector
      mainService={mainService}
      sidekickService={null}
      onChangeMain={() => {}}
      onChangeSidekick={() => {}}
      disabled={false}
    />
  )
}

afterEach(() => cleanup())

describe('ModelSelector OpenRouter integration', () => {
  it('shows Local and OpenRouter optgroups when configured', () => {
    const { container } = setup()
    const groups = [...container.querySelectorAll('optgroup')].map(g => g.label)
    // Both selects (Main + Critic) get both groups.
    expect(groups).toEqual(['Local', 'OpenRouter', 'Local', 'OpenRouter'])
    const openRouterOption = container.querySelector('option[value="openrouter:vendor/model-a"]')
    expect(openRouterOption).not.toBeNull()
    expect(openRouterOption.textContent).toBe('Model A')
  })

  it('hides the OpenRouter group when the key is not configured', () => {
    const { container } = setup({ configured: false })
    const groups = [...container.querySelectorAll('optgroup')].map(g => g.label)
    expect(groups).toEqual(['Local', 'Local'])
    expect(container.querySelector('option[value="openrouter:vendor/model-a"]')).toBeNull()
  })

  it('renders with no local services running (OpenRouter only)', () => {
    const { container } = setup({ services: [] })
    const groups = [...container.querySelectorAll('optgroup')].map(g => g.label)
    expect(groups).toEqual(['OpenRouter', 'OpenRouter'])
  })

  it('keeps a stale OpenRouter selection visible as a fallback option', () => {
    const { container } = setup({ mainService: 'openrouter:vendor/removed' })
    const fallback = container.querySelector('option[value="openrouter:vendor/removed"]')
    expect(fallback).not.toBeNull()
    expect(fallback.textContent).toContain('vendor/removed')
    expect(fallback.textContent).toContain('not in list')
    // The select still reflects the persisted value.
    const mainSelect = container.querySelectorAll('select')[0]
    expect(mainSelect.value).toBe('openrouter:vendor/removed')
  })

  it('does not add a fallback when the selection is in the curated list', () => {
    const { container } = setup({ mainService: 'openrouter:vendor/model-a' })
    const options = container.querySelectorAll('option[value="openrouter:vendor/model-a"]')
    // One per select (Main + Critic), no extra fallback entries.
    expect(options.length).toBe(2)
  })
})

describe('ModelSelector new-chat variant', () => {
  function renderNewChat({ services = LOCAL, configured = true, current = CURATED, mainService = 'vllm-test' } = {}) {
    mockRunningServices.mockReturnValue({ services, loading: false })
    mockOpenRouterModels.mockReturnValue({
      data: { configured, current, builtin: CURATED, customized: false },
      loading: false,
    })
    return render(
      <ModelSelector
        variant="new-chat"
        mainService={mainService}
        sidekickService={null}
        onChangeMain={() => {}}
        onChangeSidekick={() => {}}
        disabled={false}
      />
    )
  }

  it('renders a single model select pre-selected with the given value', () => {
    const { container } = renderNewChat()
    const selects = container.querySelectorAll('select')
    expect(selects.length).toBe(1)
    expect(selects[0].value).toBe('vllm-test')
    // No empty "Select model..." placeholder — the model is always chosen.
    expect(container.querySelector('option[value=""]')).toBeNull()
  })

  it('shows Local and OpenRouter optgroups', () => {
    const { container } = renderNewChat()
    const groups = [...container.querySelectorAll('optgroup')].map(g => g.label)
    expect(groups).toEqual(['Local', 'OpenRouter'])
  })

  it('fires onChangeMain with the new value', () => {
    const onChangeMain = vi.fn()
    mockRunningServices.mockReturnValue({ services: LOCAL, loading: false })
    mockOpenRouterModels.mockReturnValue({
      data: { configured: true, current: CURATED, builtin: CURATED, customized: false },
      loading: false,
    })
    const { container } = render(
      <ModelSelector
        variant="new-chat"
        mainService="vllm-test"
        sidekickService={null}
        onChangeMain={onChangeMain}
        onChangeSidekick={() => {}}
        disabled={false}
      />
    )
    fireEvent.change(container.querySelector('select'), { target: { value: 'openrouter:vendor/model-a' } })
    expect(onChangeMain).toHaveBeenCalledWith('openrouter:vendor/model-a')
  })
})
