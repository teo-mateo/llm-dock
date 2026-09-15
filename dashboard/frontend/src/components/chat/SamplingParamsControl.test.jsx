import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, fireEvent, cleanup, screen } from '@testing-library/react'
import SamplingParamsControl from './SamplingParamsControl'

// The hook is the seam: the control offers exactly what it reports, and the server
// decides that (dashboard/tests/test_chat_sampling_params.py pins the endpoint
// against the same mapping that builds the request).
const { mockFields } = vi.hoisted(() => ({ mockFields: vi.fn() }))
vi.mock('../../hooks/useSamplingFields', () => ({ default: (svc) => mockFields(svc) }))

const FIELDS = [
  { name: 'temperature', label: 'Temperature', kind: 'number', min: 0, max: 2, step: 0.1 },
  { name: 'top_k', label: 'Top-k', kind: 'integer', min: 0, max: 2147483647, step: null },
  { name: 'stop', label: 'Stop sequences', kind: 'strings', min: 1, max: 4, step: null },
]

function setup(opts = {}) {
  const { mainService = 'vllm-a', value = null, onChange = () => {}, disabled,
          fields = FIELDS, engine = 'vllm', loading = false, error = null } = opts
  mockFields.mockReturnValue({ engine, fields, loading, error, refresh: vi.fn() })
  return render(
    <SamplingParamsControl mainService={mainService} value={value} onChange={onChange} disabled={disabled} />
  )
}

const trigger = () => screen.getByTestId('sampling-params-control')
const openPanel = () => {
  fireEvent.click(trigger())
  return screen.getByRole('dialog')
}
const setField = (name, raw) =>
  fireEvent.change(screen.getByTestId('sampling-field-' + name), { target: { value: raw } })

afterEach(() => cleanup())

describe('SamplingParamsControl', () => {
  it('renders nothing while the field list is loading', () => {
    const { container } = setup({ loading: true })
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when the engine takes nothing and nothing is stored', () => {
    const { container } = setup({ fields: [] })
    expect(container.firstChild).toBeNull()
  })

  it('shows a clearable warning when params are stored but the engine takes none', () => {
    // A model switch must not leave a setting that is neither shown nor removable.
    const onChange = vi.fn()
    setup({ fields: [], value: { temperature: 0.5 }, onChange })
    expect(trigger().textContent).toMatch(/sampling unused/)
    fireEvent.click(trigger())
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('shows the stored field count on the trigger', () => {
    setup({ value: { temperature: 0.2, top_k: 5 } })
    expect(trigger().textContent).toMatch(/sampling . 2/)
  })

  it('offers one row per field the service takes', () => {
    setup()
    openPanel()
    expect(screen.getByTestId('sampling-field-temperature')).toBeTruthy()
    expect(screen.getByTestId('sampling-field-stop')).toBeTruthy()
    expect(screen.queryByTestId('sampling-field-min_p')).toBeNull()
  })

  it('pre-fills stored values, so a whole-blob replace is visible before it saves', () => {
    setup({ value: { temperature: 0.4, stop: ['A', 'B'] } })
    openPanel()
    expect(screen.getByTestId('sampling-field-temperature').value).toBe('0.4')
    expect(screen.getByTestId('sampling-field-stop').value).toBe('A, B')
  })

  it('sends only the fields that carry a value', () => {
    const onChange = vi.fn()
    setup({ onChange })
    openPanel()
    setField('temperature', '1.4')
    fireEvent.click(screen.getByTestId('sampling-apply'))
    expect(onChange).toHaveBeenCalledWith({ temperature: 1.4 })
  })

  it('sends null when every field is left unset', () => {
    const onChange = vi.fn()
    setup({ value: { temperature: 0.4 }, onChange })
    openPanel()
    setField('temperature', '')
    fireEvent.click(screen.getByTestId('sampling-apply'))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('sends null when Clear is clicked', () => {
    const onChange = vi.fn()
    setup({ value: { temperature: 0.4 }, onChange })
    openPanel()
    fireEvent.click(screen.getByTestId('sampling-clear'))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('parses stop sequences into a trimmed list', () => {
    const onChange = vi.fn()
    setup({ onChange })
    openPanel()
    setField('stop', ' ALPHA , BETA ')
    fireEvent.click(screen.getByTestId('sampling-apply'))
    expect(onChange).toHaveBeenCalledWith({ stop: ['ALPHA', 'BETA'] })
  })

  it('refuses to send a value above the bound the server published', () => {
    const onChange = vi.fn()
    setup({ onChange })
    openPanel()
    setField('temperature', '3')
    fireEvent.click(screen.getByTestId('sampling-apply'))
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByTestId('sampling-error-temperature').textContent).toMatch(/max 2/)
  })

  it('refuses a fractional top_k, which the server would reject as a float', () => {
    const onChange = vi.fn()
    setup({ onChange })
    openPanel()
    setField('top_k', '4.5')
    fireEvent.click(screen.getByTestId('sampling-apply'))
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByTestId('sampling-error-top_k').textContent).toMatch(/whole number/)
  })

  it('reports a load failure instead of rendering an empty control', () => {
    // An empty control reads as "this model has no knobs". The dashboard being
    // unreachable is a different fact and must not look like a property of the model.
    setup({ fields: [], error: 'HTTP 500' })
    expect(trigger().textContent).toMatch(/sampling$/)
    openPanel()
    expect(screen.getByText(/HTTP 500/)).toBeTruthy()
  })

  it('is disabled with the composer', () => {
    setup({ disabled: true })
    expect(trigger().disabled).toBe(true)
  })
})
