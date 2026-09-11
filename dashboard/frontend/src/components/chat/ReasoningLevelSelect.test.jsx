import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, fireEvent, cleanup, screen } from '@testing-library/react'
import ReasoningLevelSelect from './ReasoningLevelSelect'

const { mockServices } = vi.hoisted(() => ({ mockServices: vi.fn() }))
vi.mock('../../hooks/useServicesSSE', () => ({ default: (...a) => mockServices(...a) }))

const withLevels = (levels, status = 'running') => [{
  name: 'llamacpp-qwen38',
  status,
  reasoning_levels: levels.map(id => ({ id, effort: id })),
}]

function setup({ services, mainService = 'llamacpp-qwen38', value = null, onChange = () => {}, disabled }) {
  mockServices.mockReturnValue({ services, loading: false })
  return render(
    <ReasoningLevelSelect
      mainService={mainService}
      value={value}
      onChange={onChange}
      disabled={disabled}
    />
  )
}

const trigger = () => screen.getByTestId('reasoning-level-select')
const openList = () => {
  fireEvent.click(trigger())
  return screen.getByRole('listbox')
}
const optionLabels = () => [...screen.getAllByRole('option')].map(o => o.textContent.replace(/not offered by this model$/, '').trim())

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

  it('renders nothing while services are still loading', () => {
    mockServices.mockReturnValue({ services: null, loading: true })
    const { container } = render(
      <ReasoningLevelSelect mainService="llamacpp-qwen38" value={null} onChange={() => {}} />
    )
    expect(container.firstChild).toBeNull()
  })

  // A level for a stopped service is valid server-side, so the ladder must show.
  it('offers the ladder for a stopped service too', () => {
    setup({ services: withLevels(['off', 'low'], 'exited'), value: 'low' })
    expect(trigger().textContent).toContain('low')
    openList()
    expect(optionLabels()).toEqual(['Model default', 'off', 'low'])
  })

  it('keeps a stored level visible and clearable after the ladder was cleared', () => {
    // A stored level with no ladder stays visible and clearable.
    const onChange = vi.fn()
    setup({ services: withLevels([]), value: 'low', onChange })
    expect(trigger().textContent).toContain('low')
    expect(trigger().className).toContain('text-critique')
    openList()
    expect(optionLabels()).toEqual(['Model default', 'low'])
    fireEvent.click(screen.getByRole('option', { name: /Model default/ }))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('carries no visible "Reasoning:" label — the control speaks for itself', () => {
    setup({ services: withLevels(['off', 'low']) })
    expect(screen.queryByText(/reasoning/i)).toBeNull()
    expect(trigger().getAttribute('aria-label')).toContain('Reasoning level')
  })

  it('is a collapsed button until opened, so the composer stays narrow', () => {
    setup({ services: withLevels(['off', 'low']) })
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(trigger().getAttribute('aria-expanded')).toBe('false')
  })

  it('offers the declared ladder in declaration order plus a model default', () => {
    setup({ services: withLevels(['off', 'low', 'medium', 'xhigh']) })
    openList()
    expect(optionLabels()).toEqual(['Model default', 'off', 'low', 'medium', 'xhigh'])
  })

  it('names the current choice on the trigger, model default when unset', () => {
    setup({ services: withLevels(['off', 'low']), value: null })
    expect(trigger().getAttribute('aria-label')).toBe('Reasoning level: model default')
    cleanup()
    setup({ services: withLevels(['off', 'low']), value: 'low' })
    expect(trigger().getAttribute('aria-label')).toBe('Reasoning level: low')
    expect(trigger().textContent).toContain('low')
  })

  it('marks the stored level selected when the list opens', () => {
    setup({ services: withLevels(['off', 'low', 'xhigh']), value: 'xhigh' })
    openList()
    const selected = screen.getAllByRole('option').filter(o => o.getAttribute('aria-selected') === 'true')
    expect(selected).toHaveLength(1)
    expect(selected[0].textContent).toContain('xhigh')
  })

  it('reports a picked level by id', () => {
    const onChange = vi.fn()
    setup({ services: withLevels(['off', 'low', 'medium']), onChange })
    openList()
    fireEvent.click(screen.getByRole('option', { name: /medium/ }))
    expect(onChange).toHaveBeenCalledWith('medium')
  })

  it('reports the model default as null rather than an empty string', () => {
    const onChange = vi.fn()
    setup({ services: withLevels(['off', 'low']), value: 'low', onChange })
    openList()
    fireEvent.click(screen.getByRole('option', { name: /Model default/ }))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('closes after a pick, so the composer does not stay covered', () => {
    setup({ services: withLevels(['off', 'low']) })
    openList()
    fireEvent.click(screen.getByRole('option', { name: /off/ }))
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('opens and moves on the keyboard, choosing with Enter', () => {
    const onChange = vi.fn()
    setup({ services: withLevels(['off', 'low']), onChange })
    fireEvent.keyDown(trigger(), { key: 'ArrowDown' })
    expect(screen.getByRole('listbox')).toBeTruthy()
    fireEvent.keyDown(trigger(), { key: 'ArrowDown' })
    fireEvent.keyDown(trigger(), { key: 'Enter' })
    // Index 1 of [Model default, off, low] is 'off'.
    expect(onChange).toHaveBeenCalledWith('off')
  })

  it('clamps at the ends of the list instead of wrapping out of range', () => {
    const onChange = vi.fn()
    setup({ services: withLevels(['off']), onChange })
    fireEvent.keyDown(trigger(), { key: 'ArrowUp' })
    fireEvent.keyDown(trigger(), { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('closes on Escape and returns focus to the trigger', () => {
    setup({ services: withLevels(['off', 'low']) })
    openList()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(document.activeElement).toBe(trigger())
  })

  it('closes on a click outside, e.g. back into the textarea', () => {
    const { container } = setup({ services: withLevels(['off', 'low']) })
    openList()
    fireEvent.pointerDown(container.ownerDocument.body)
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('keeps a level the service no longer offers visible, flagged, and selectable', () => {
    setup({ services: withLevels(['off', 'low']), value: 'thinking' })
    expect(trigger().textContent).toContain('thinking')
    expect(trigger().className).toContain('text-critique')
    openList()
    const stale = screen.getByRole('option', { name: /thinking/ })
    expect(stale.textContent).toContain('not offered by this model')
    expect(stale.getAttribute('aria-selected')).toBe('true')
  })

  it('is disabled by the caller, e.g. mid-run', () => {
    setup({ services: withLevels(['off', 'low']), disabled: true })
    expect(trigger().disabled).toBe(true)
  })

  // Icons are the point of the control, and a name missing from the free icon
  // set renders as an empty box — fa-gauge-low is pro-only and must not appear.
  it.each([
    ['off', 'fa-ban'],
    ['low', 'fa-feather'],
    ['minimal', 'fa-feather'],
    ['medium', 'fa-gauge-simple'],
    ['high', 'fa-gauge'],
    ['xhigh', 'fa-gauge-high'],
    ['max', 'fa-gauge-high'],
    ['dragon', 'fa-brain'],
  ])('maps level %s to icon %s', (level, icon) => {
    setup({ services: withLevels([level]), value: level })
    expect(trigger().querySelector('i')).toHaveClass(icon)
    expect(trigger().innerHTML).not.toContain('fa-gauge-low')
  })

  it('shows the model-default icon when nothing is stored', () => {
    setup({ services: withLevels(['off']), value: null })
    expect(trigger().querySelector('i')).toHaveClass('fa-wand-magic-sparkles')
  })
})
