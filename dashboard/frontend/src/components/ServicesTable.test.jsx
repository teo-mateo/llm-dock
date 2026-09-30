import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ServicesTable from './ServicesTable'

// The badge is driven by the service payload: the SSE delta (metadata-changed)
// rewrites the service object in the hook's state, so re-rendering the table
// with a changed `inspect` field is the exact path the live delta takes.
let mockServices = []

vi.mock('../api', () => ({
  fetchAPI: vi.fn().mockResolvedValue({}),
}))

vi.mock('../hooks/useServicesSSE', () => ({
  default: () => ({
    services: mockServices,
    error: null,
    connected: true,
    loading: false,
    total: mockServices.length,
    running: mockServices.filter(s => s.status === 'running').length,
    stopped: mockServices.length,
    refresh: vi.fn(),
    toggleFavorite: vi.fn(),
  }),
}))

const svc = (name, over = {}) => ({
  name,
  status: 'not-created',
  host_port: 3302,
  favorite: false,
  api_key: null,
  model_size_str: null,
  openwebui_registered: false,
  ...over,
})

function renderTable() {
  const view = render(
    <MemoryRouter>
      <ServicesTable />
    </MemoryRouter>
  )
  // Desktop and mobile renderings both carry the badge; the assertions target
  // the desktop table only.
  const table = screen.getAllByRole('table').find((t) => t.textContent)
  return { ...view, table }
}

afterEach(() => {
  cleanup()
  mockServices = []
})

describe('ServicesTable inspect badge', () => {
  it('shows the badge only for inspected services', () => {
    mockServices = [
      svc('llamacpp-a', { status: 'running', inspect: true }),
      svc('vllm-b', { inspect: false }),
      svc('ds4-c'),
    ]

    const { table } = renderTable()

    const badges = within(table).getAllByTitle('Request inspection is on')
    expect(badges).toHaveLength(1)
    expect(badges[0].textContent).toContain('inspect')
    // The badge sits in the name cell of the inspected row only.
    const inspectedRow = within(table).getByText('llamacpp-a').closest('td')
    expect(inspectedRow).toHaveTextContent('inspect')
    expect(within(table).getByText('vllm-b').closest('td')).not.toHaveTextContent('inspect')
    expect(within(table).getByText('ds4-c').closest('td')).not.toHaveTextContent('inspect')
  })

  it('follows an inspect change in props without a refetch', () => {
    mockServices = [svc('llamacpp-a', { inspect: false })]
    const { table, rerender } = renderTable()

    expect(within(table).queryAllByTitle('Request inspection is on')).toHaveLength(0)

    // The metadata-changed delta path: same service object identity flow,
    // the field flips, the table re-renders, the badge appears.
    mockServices = [svc('llamacpp-a', { inspect: true })]
    rerender(
      <MemoryRouter>
        <ServicesTable />
      </MemoryRouter>
    )
    expect(within(table).getAllByTitle('Request inspection is on')).toHaveLength(1)

    // And it disappears again when the field flips back.
    mockServices = [svc('llamacpp-a', { inspect: false })]
    rerender(
      <MemoryRouter>
        <ServicesTable />
      </MemoryRouter>
    )
    expect(within(table).queryAllByTitle('Request inspection is on')).toHaveLength(0)
  })

  it('the badge carries the magnifier icon', () => {
    mockServices = [svc('llamacpp-a', { inspect: true })]

    const { table } = renderTable()

    const badge = within(table).getByTitle('Request inspection is on')
    expect(badge.querySelector('i.fa-magnifying-glass')).toBeTruthy()
  })
})

describe('ServicesTable missing-model warning', () => {
  it('warns only on a service whose model files are gone', () => {
    mockServices = [
      svc('llamacpp-gone', {
        model_missing: true,
        model_host_path: '/home/u/.cache/huggingface/hub/models--x/snapshots/a/gone.gguf',
      }),
      svc('llamacpp-here', { model_size_str: '18.42 GB' }),
    ]

    const { table } = renderTable()

    const warning = within(table).getAllByText('model missing')
    expect(warning).toHaveLength(1)
    expect(within(table).getByText('llamacpp-gone').closest('td')).toHaveTextContent('model missing')
    expect(within(table).getByText('llamacpp-here').closest('td')).not.toHaveTextContent('model missing')

    const warningTitle = within(table).getByTitle(
      /Model files are not on disk, so this service cannot load them/
    ).title
    expect(warningTitle).toContain('Expected at /home/u/.cache')

    // The size cell stops pretending there is merely nothing to measure.
    const goneSize = within(table).getByText('llamacpp-gone').closest('tr').querySelectorAll('td')[4]
    expect(goneSize.textContent).toBe('Missing')
    expect(within(table).getByText('llamacpp-here').closest('tr').querySelectorAll('td')[4].textContent).toBe('18.42 GB')
    expect(within(table).getByText('llamacpp-here').closest('tr').querySelectorAll('td')[4].textContent).not.toBe('Missing')
  })

  it('carries a warning icon', () => {
    mockServices = [svc('llamacpp-gone', { model_missing: true })]

    const { table } = renderTable()

    const badge = within(table).getByTitle(/Model files are not on disk/)
    expect(badge.querySelector('i.fa-triangle-exclamation')).toBeTruthy()
  })

  it('shows the warning on the mobile card too', () => {
    mockServices = [svc('llamacpp-gone', { model_missing: true })]

    render(
      <MemoryRouter>
        <ServicesTable />
      </MemoryRouter>
    )

    expect(screen.getAllByText('model missing').length).toBeGreaterThan(1)
  })
})
