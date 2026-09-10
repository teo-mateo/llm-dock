import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, fireEvent, cleanup } from '@testing-library/react'
import ReasoningLevelSelect from './ReasoningLevelSelect'

const { mockRunningServices } = vi.hoisted(() => ({ mockRunningServices: vi.fn() }))
vi.mock('../../hooks/useRunningServices', () => ({ default: (...a) => mockRunningServices(...a) }))

const withLevels = (levels) => [{
  name: 'llamacpp-qwen38',
  status: 'running',
  reasoning_levels: levels.map(id => ({ id, effort: id })),
}]

function setup({ services, mainService = 'llamacpp-qwen38', value = null, onChange = () => {} }) {
  mockRunningServices.mockReturnValue({ services, loading: false })
  return render(
    <ReasoningLevelSelect mainService={mainService} value={value} onChange={onChange} />
  )
}

afterEach(() => cleanup())

describe('ReasoningLevelSelect', () => {
  it('renders nothing when the service declares no levels', () => {
    const { container } = setup({ services: [{ name: 'llamacpp-qwen38', reasoning_levels: [] }] })
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing for a service absent from the payload, e.g. OpenRouter', () => {
    const { container } = setup({ services: [], mainService: 'openrouter:vendor/model-a' })
    expect(container.firstChild).toBeNull()
  })

  it('offers the declared ladder in declaration order plus a model default', () => {
    const { container } = setup({ services: withLevels(['off', 'low', 'medium', 'xhigh']) })
    const options = [...container.querySelectorAll('option')].map(o => o.value)
    // '' is "say nothing to the model", distinct from the declared 'off'.
    expect(options).toEqual(['', 'off', 'low', 'medium', 'xhigh'])
  })

  it('shows model default when no level is selected', () => {
    const { container } = setup({ services: withLevels(['off', 'low']), value: null })
    expect(container.querySelector('select').value).toBe('')
  })

  it('selects the stored level', () => {
    const { container } = setup({ services: withLevels(['off', 'low', 'xhigh']), value: 'xhigh' })
    expect(container.querySelector('select').value).toBe('xhigh')
  })

  it('keeps a level the service no longer offers visible and labelled', () => {
    const { container } = setup({ services: withLevels(['off', 'low']), value: 'thinking' })
    const select = container.querySelector('select')
    expect(select.value).toBe('thinking')
    const stale = container.querySelector('option[value="thinking"]')
    expect(stale.textContent).toContain('not offered by this model')
  })

  it('reports an empty choice as null rather than an empty string', () => {
    const onChange = vi.fn()
    const { container } = setup({ services: withLevels(['off', 'low']), value: 'low', onChange })
    fireEvent.change(container.querySelector('select'), { target: { value: '' } })
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('reports a picked level by id', () => {
    const onChange = vi.fn()
    const { container } = setup({ services: withLevels(['off', 'low', 'medium']), onChange })
    fireEvent.change(container.querySelector('select'), { target: { value: 'medium' } })
    expect(onChange).toHaveBeenCalledWith('medium')
  })

  it('renders nothing while services are still loading', () => {
    mockRunningServices.mockReturnValue({ services: [], loading: true })
    const { container } = render(
      <ReasoningLevelSelect mainService="llamacpp-qwen38" value={null} onChange={() => {}} />
    )
    expect(container.firstChild).toBeNull()
  })
})
