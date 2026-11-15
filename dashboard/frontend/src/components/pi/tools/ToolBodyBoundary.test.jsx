import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import ToolBodyBoundary from './ToolBodyBoundary'
import PiToolDetails from '../PiToolDetails'

const Throws = () => {
  throw new Error('bad payload')
}

function tool(output) {
  return {
    item: { id: 't1', name: 'bash', args: '{"command":"ls"}', output, status: 'done', durationMs: null, truncated: false },
    args: { command: 'ls' },
    result: { text: output, images: [], details: null, structured: null, isError: false },
    view: { command: 'ls' },
  }
}

afterEach(cleanup)

describe('ToolBodyBoundary', () => {
  it('a viewer that throws falls back to the generic view', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ToolBodyBoundary tool={tool('out')} resetKey={1}>
        <Throws />
      </ToolBodyBoundary>,
    )
    expect(screen.getByText('command')).toBeInTheDocument()
    expect(screen.getByText('out')).toBeInTheDocument()
    vi.restoreAllMocks()
  })

  it('a new result retries the viewer', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const { rerender } = render(
      <ToolBodyBoundary tool={tool('out')} resetKey={1}>
        <Throws />
      </ToolBodyBoundary>,
    )
    rerender(
      <ToolBodyBoundary tool={tool('out')} resetKey={2}>
        <span>fixed</span>
      </ToolBodyBoundary>,
    )
    expect(screen.getByText('fixed')).toBeInTheDocument()
    vi.restoreAllMocks()
  })

  it('a throwing registered viewer does not break the details panel', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const views = { bash: { parse: () => ({}), summary: () => '', Body: Throws } }
    render(<PiToolDetails tool={tool('out')} views={views} />)
    expect(screen.getByText('out')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Raw ▸' })).toBeInTheDocument()
    vi.restoreAllMocks()
  })
})
