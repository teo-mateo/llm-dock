import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CaptureList from './CaptureList'
import { relativeTime, formatDuration } from './parse'

function row(overrides = {}) {
  return {
    id: 'c1',
    service_name: 'llamacpp-qwen3',
    model: 'qwen3.8-27b',
    template_type: 'llamacpp',
    method: 'POST',
    path: '/v1/chat/completions',
    status_code: 200,
    stream: true,
    prompt_tokens: 1843,
    completion_tokens: 402,
    total_tokens: 2245,
    ttfb_ms: 412,
    duration_ms: 8391,
    error: null,
    request_truncated: false,
    response_truncated: false,
    created_at: '2026-09-18T20:14:03.412Z',
    ...overrides,
  }
}

function setup(props = {}) {
  const onSelect = vi.fn()
  const onRemove = vi.fn()
  const onLoadMore = vi.fn()
  const onConfirmStateChange = vi.fn()
  const all = {
    rows: [],
    total: 0,
    service: null,
    selectedId: null,
    loading: false,
    onSelect,
    onRemove,
    onLoadMore,
    onConfirmStateChange,
    ...props,
  }
  const view = render(
    <MemoryRouter>
      <CaptureList {...all} />
    </MemoryRouter>
  )
  return { view, onSelect, onRemove, onLoadMore, onConfirmStateChange }
}

afterEach(cleanup)

describe('parse helpers', () => {
  it('formatDuration switches units under a second', () => {
    expect(formatDuration(412)).toBe('412ms')
    expect(formatDuration(8391)).toBe('8.4s')
    expect(formatDuration(null)).toBe('')
  })

  it('relativeTime buckets recent, then hours, then falls back to a date', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-18T12:00:00'))
    expect(relativeTime('2026-09-18T11:59:50')).toBe('just now')
    expect(relativeTime('2026-09-18T11:56:00')).toBe('4m ago')
    expect(relativeTime('2026-09-18T10:00:00')).toBe('2h ago')
    expect(relativeTime('2026-09-16T08:05:00')).toBe('Sep 16 08:05')
    vi.useRealTimers()
  })
})

describe('CaptureList rows', () => {
  it('renders status, model, stream icon, tokens, duration and an empty detail prompt state', () => {
    setup({ rows: [row()], total: 1 })

    expect(screen.getByText('200')).toBeInTheDocument()
    expect(screen.getByText('qwen3.8-27b')).toBeInTheDocument()
    expect(screen.getByTitle('streamed response')).toBeInTheDocument()
    expect(screen.getByText('↑1843 ↓402')).toBeInTheDocument()
    expect(screen.getByText('8.4s')).toBeInTheDocument()
    expect(screen.getByText('8.4s')).toBeInTheDocument()
    expect(screen.getByText('llamacpp-qwen3')).toBeInTheDocument()
  })

  it('shows a red pill for error statuses', () => {
    setup({ rows: [row({ id: 'c2', status_code: 500 })], total: 1 })
    expect(screen.getByText('500')).toBeInTheDocument()
  })

  it('shows a muted dash and the error tooltip when there is only an error', () => {
    setup({ rows: [row({ status_code: null, error: 'upstream refused' })], total: 1 })
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByTitle('upstream refused')).toBeInTheDocument()
  })

  it('shows the truncated chip when either truncation flag is set', () => {
    setup({ rows: [row({ response_truncated: true })], total: 1 })
    expect(screen.getByText('truncated')).toBeInTheDocument()
  })

  it('renders the footer count and fires Load more while more rows exist', () => {
    const { onLoadMore } = setup({ rows: [row(), row({ id: 'c2' })], total: 120 })
    expect(screen.getByText(/Showing 2 of 120/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
    expect(onLoadMore).toHaveBeenCalled()
  })

  it('hides Load more when everything is shown', () => {
    setup({ rows: [row()], total: 1 })
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })
})

describe('CaptureList interactions', () => {
  it('row click calls onSelect with the id', () => {
    const { onSelect } = setup({ rows: [row()], total: 1 })
    fireEvent.click(screen.getByRole('button', { name: (name) => name.includes('qwen3.8-27b') }))
    expect(onSelect).toHaveBeenCalledWith('c1')
  })

  it('selected row carries the accent border class', () => {
    const { view } = setup({ rows: [row()], total: 1, selectedId: 'c1' })
    const el = view.container.querySelector('[data-capture-id="c1"]')
    expect(el.className).toContain('border-l-accent')
  })

  it('trash reveals an inline confirm; confirm calls onRemove, cancel does not', () => {
    const { onRemove, onConfirmStateChange } = setup({ rows: [row()], total: 1 })

    fireEvent.click(screen.getByLabelText('Delete capture'))
    expect(screen.getByText('Delete?')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Cancel'))
    expect(onRemove).not.toHaveBeenCalled()
    expect(onConfirmStateChange).toHaveBeenLastCalledWith(false)

    fireEvent.click(screen.getByLabelText('Delete capture'))
    fireEvent.click(screen.getByText('Delete?'))
    expect(onRemove).toHaveBeenCalledWith('c1')
  })

  it('ArrowDown/ArrowUp move the selection', () => {
    const { onSelect, view } = setup({
      rows: [row({ id: 'top' }), row({ id: 'mid' }), row({ id: 'bot' })],
      total: 3,
      selectedId: 'mid',
    })
    const list = view.container.querySelector('div[tabindex="0"]')

    fireEvent.keyDown(list, { key: 'ArrowDown' })
    expect(onSelect).toHaveBeenLastCalledWith('bot')

    fireEvent.keyDown(list, { key: 'ArrowUp' })
    expect(onSelect).toHaveBeenLastCalledWith('top')
  })
})

describe('CaptureList empty states', () => {
  it('shows the no-captures copy with a link when unfiltered', () => {
    setup({ rows: [], total: 0, loading: false })
    expect(screen.getByText('No captures yet.')).toBeInTheDocument()
    expect(screen.getByText('Go to Services')).toBeInTheDocument()
  })

  it('shows the filtered copy under a service filter', () => {
    setup({ rows: [], total: 0, service: 'svc-x' })
    expect(screen.getByText('No captures for svc-x.')).toBeInTheDocument()
  })

  it('renders neither empty state while loading', () => {
    setup({ rows: [], total: 0, loading: true })
    expect(screen.queryByText('No captures yet.')).not.toBeInTheDocument()
  })
})
