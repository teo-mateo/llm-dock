import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import PiSessionList from './PiSessionList'

function session(overrides = {}) {
  return {
    session_id: 's1',
    instance_id: 'i1',
    name: 'llm-dock',
    cwd: '/github/teo-mateo/llm-dock',
    state: 'working',
    live: true,
    ...overrides,
  }
}

function setup(props = {}) {
  const onSelect = vi.fn()
  const onToggleLiveOnly = vi.fn()
  render(
    <PiSessionList
      sessions={[]}
      selectedKey={null}
      onSelect={onSelect}
      liveOnly={true}
      onToggleLiveOnly={onToggleLiveOnly}
      {...props}
    />,
  )
  return { onSelect, onToggleLiveOnly }
}

afterEach(cleanup)

describe('PiSessionList', () => {
  it('renders label text not only colour', () => {
    setup({ sessions: [session()] })
    expect(screen.getByText('working')).toBeInTheDocument()
    expect(screen.getByText('llm-dock')).toBeInTheDocument()
  })

  it('live only hides ended sessions', () => {
    setup({
      sessions: [
        session({ session_id: 'live', name: 'live', state: 'working', live: true }),
        session({ session_id: 'gone', name: 'old', state: null, live: false }),
      ],
    })
    expect(screen.getByText('live')).toBeInTheDocument()
    expect(screen.queryByText('old')).not.toBeInTheDocument()
  })

  it('empty state', () => {
    setup()
    expect(
      screen.getByText('No pi sessions yet — start pi with the pi-remote extension.'),
    ).toBeInTheDocument()
  })

  it('click selects the session', () => {
    const s = session()
    const { onSelect } = setup({ sessions: [s] })
    fireEvent.click(screen.getByRole('button', { name: /llm-dock/ }))
    expect(onSelect).toHaveBeenCalledWith(s)
  })

  it('keeps every question in one compact line', () => {
    setup({
      sessions: [
        session({ prompts: [{ prompt_id: 'a' }, { prompt_id: 'b' }] }),
        session({ session_id: 's2', name: 'troostwijk', state: 'idle' }),
      ],
    })
    const rows = screen.getAllByRole('button')
    expect(rows).toHaveLength(2)
    for (const row of rows) {
      expect(row).toHaveClass('py-1.5')
      expect(row).not.toHaveClass('p-3')
      expect(row).toHaveClass('items-center')
      expect(row).not.toHaveClass('flex-col')
      expect(row).toHaveClass('max-sm:min-h-11')
      expect(row).toHaveClass('focus-visible:ring-2')
    }
  })

  it('carries the full path in the row title so truncation loses nothing', () => {
    setup({ sessions: [session()] })
    expect(screen.getByRole('button', { name: /llm-dock/ })).toHaveAttribute(
      'title',
      'llm-dock — /github/teo-mateo/llm-dock',
    )
  })

  it('lets a long path yield before the name and the controls', () => {
    setup({
      sessions: [
        session({
          name: 'a-pretty-long-session-name',
          cwd: '/'.repeat(60),
          prompts: [{ prompt_id: 'a' }, { prompt_id: 'b' }],
        }),
      ],
    })
    const row = screen.getByRole('button', { name: /a-pretty-long-session-name/ })
    const name = row.querySelectorAll('span.truncate')[0]
    const path = row.querySelectorAll('span.truncate')[1]
    expect(name).toHaveClass('flex-1')
    expect(path.className).toContain('shrink-[3]')
    expect(path).toHaveClass('sm:hidden')
    expect(screen.getByLabelText('2 questions waiting')).toHaveClass('flex-none')
    expect(row.lastElementChild).toHaveClass('flex-none')
  })
})

it('shows the tail of a long path so the row still says where the session runs', () => {
    setup({
      sessions: [
        session({ name: null, cwd: '/github/very/long/path/to/a/deeply/nested/experiment-repo-2026' }),
      ],
    })
    const row = screen.getByRole('button', { name: /experiment-repo-2026/ })
    expect(row).toHaveTextContent('nested/experiment-repo-2026')
    expect(row.textContent).not.toContain('/github/very/long/path')
    expect(row).toHaveAttribute(
      'title',
      'experiment-repo-2026 — /github/very/long/path/to/a/deeply/nested/experiment-repo-2026',
    )
  })

describe('needs-answer indicator', () => {
  it('marks a live session with an open question', () => {
    setup({ sessions: [session({ prompts: [{ prompt_id: 'a' }] })] })
    expect(screen.getByLabelText('1 question waiting')).toHaveTextContent('1 waiting')
  })

  it('counts several open questions', () => {
    setup({ sessions: [session({ prompts: [{ prompt_id: 'a' }, { prompt_id: 'b' }] })] })
    expect(screen.getByLabelText('2 questions waiting')).toHaveTextContent('2 waiting')
  })

  it('says nothing for a session with no questions', () => {
    setup({ sessions: [session()] })
    expect(screen.queryByText(/waiting/)).not.toBeInTheDocument()
  })

  it('says nothing for an ended session that still has a stored question', () => {
    setup({ sessions: [session({ live: false, prompts: [{ prompt_id: 'a' }] })] })
    expect(screen.queryByText(/waiting/)).not.toBeInTheDocument()
  })
})
