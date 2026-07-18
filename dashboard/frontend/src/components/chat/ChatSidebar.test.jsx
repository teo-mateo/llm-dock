import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import ChatSidebar from './ChatSidebar'

// ThemeSwitcher pulls in unrelated context (icons, theme store). Stub it.
vi.mock('../ThemeSwitcher', () => ({ default: () => null }))

afterEach(() => cleanup())

// Tree shape used by the range tests:
//   A
//     A1   (spinoff of A)
//   B
//   C
//     C1   (spinoff of C)
//   D
// flatOrder (depth-first) is therefore: A, A1, B, C, C1, D.
const conversations = [
  { id: 'A',  title: 'A',  parent_conversation_id: null, updated_at: '2026-01-01' },
  { id: 'A1', title: 'A1', parent_conversation_id: 'A',  updated_at: '2026-01-01' },
  { id: 'B',  title: 'B',  parent_conversation_id: null, updated_at: '2026-01-01' },
  { id: 'C',  title: 'C',  parent_conversation_id: null, updated_at: '2026-01-01' },
  { id: 'C1', title: 'C1', parent_conversation_id: 'C',  updated_at: '2026-01-01' },
  { id: 'D',  title: 'D',  parent_conversation_id: null, updated_at: '2026-01-01' },
]

function renderSidebar(overrides) {
  return render(
    <ChatSidebar
      conversations={conversations}
      activeId={null}
      onSelect={() => {}}
      onCreate={() => {}}
      onDelete={() => {}}
      onDeleteMany={() => {}}
      collapsed={false}
      onCollapse={() => {}}
      onExpand={() => {}}
      {...overrides}
    />
  )
}

// Returns the label that wraps the conversation row's checkbox. The
// label is the actual click target — it's a 32px hit area around a 14px
// <input>, and the toggle handler lives on the label so that clicks on
// the padding behave the same as clicks on the input itself.
function checkboxFor(title) {
  const titleNode = screen.getByText(title)
  const row = titleNode.closest('.group')
  return within(row).getByRole('checkbox').closest('label')
}

function selectedTitles() {
  // All checked checkboxes, mapped back to their row's title text. Order
  // matches the rendered DOM order, which is the same as flatOrder.
  return screen
    .getAllByRole('checkbox')
    .filter(cb => cb.checked)
    .map(cb => within(cb.closest('.group')).getAllByText(/^[A-Z]\d?$/)[0].textContent)
}

describe('ChatSidebar shift-click range selection', () => {
  it('plain click toggles a single row and sets the anchor', () => {
    renderSidebar()
    fireEvent.click(checkboxFor('B'))
    expect(selectedTitles()).toEqual(['B'])
  })

  it('shift-click without an anchor falls back to a single toggle', () => {
    renderSidebar()
    // First interaction is a shift-click — no prior anchor exists, so it
    // should just toggle the clicked row.
    fireEvent.click(checkboxFor('C'), { shiftKey: true })
    expect(selectedTitles()).toEqual(['C'])
  })

  it('shift-click selects the inclusive depth-first range between anchor and clicked', () => {
    renderSidebar()
    fireEvent.click(checkboxFor('A'))                       // anchor = A
    fireEvent.click(checkboxFor('C1'), { shiftKey: true })  // range A..C1
    // flatOrder slice from A to C1 is A, A1, B, C, C1.
    expect(selectedTitles()).toEqual(['A', 'A1', 'B', 'C', 'C1'])
  })

  it('range works in reverse (clicked above anchor) and includes both endpoints', () => {
    renderSidebar()
    fireEvent.click(checkboxFor('D'))                      // anchor = D
    fireEvent.click(checkboxFor('A1'), { shiftKey: true }) // range A1..D
    expect(selectedTitles()).toEqual(['A1', 'B', 'C', 'C1', 'D'])
  })

  it('anchor persists across consecutive shift-clicks (Finder/Gmail behavior)', () => {
    renderSidebar()
    fireEvent.click(checkboxFor('A'))                      // anchor = A
    fireEvent.click(checkboxFor('B'), { shiftKey: true })  // range A..B
    fireEvent.click(checkboxFor('D'), { shiftKey: true })  // range A..D, anchor still A
    expect(selectedTitles()).toEqual(['A', 'A1', 'B', 'C', 'C1', 'D'])
  })

  // Direct clicks on the 14px <input> itself take a different code path
  // from label-padding clicks: the input's own onClick stops propagation
  // (so the label's preventDefault never cancels the native toggle) and
  // toggles selection itself. These tests click the input element
  // directly so a regression in either duplicated input handler — or a
  // reintroduced preventDefault that desyncs the visible checkbox from
  // selection state — fails here even while the label-padding tests stay
  // green.
  function inputFor(title) {
    const row = screen.getByText(title).closest('.group')
    return within(row).getByRole('checkbox')
  }

  it('clicking directly on a root checkbox input selects it and checks the box', () => {
    renderSidebar()
    fireEvent.click(inputFor('B'))
    expect(inputFor('B').checked).toBe(true)
    expect(selectedTitles()).toEqual(['B'])
  })

  it('clicking directly on a spinoff checkbox input selects it and checks the box', () => {
    renderSidebar()
    fireEvent.click(inputFor('A1'))
    expect(inputFor('A1').checked).toBe(true)
    expect(selectedTitles()).toEqual(['A1'])
  })

  it('shift-clicking directly on an input extends the range from the anchor', () => {
    renderSidebar()
    fireEvent.click(inputFor('A'))                      // anchor = A
    fireEvent.click(inputFor('C'), { shiftKey: true })  // range A..C
    expect(selectedTitles()).toEqual(['A', 'A1', 'B', 'C'])
  })

  it('clicking a selected input directly deselects it', () => {
    renderSidebar()
    fireEvent.click(inputFor('B'))
    fireEvent.click(inputFor('B'))
    expect(inputFor('B').checked).toBe(false)
    expect(selectedTitles()).toEqual([])
  })

  it('Clear resets the anchor so the next shift-click no longer extends the old range', () => {
    renderSidebar()
    fireEvent.click(checkboxFor('A'))                       // anchor = A
    fireEvent.click(checkboxFor('B'), { shiftKey: true })   // range A..B
    fireEvent.click(screen.getByTitle('Clear selection'))   // clears + drops anchor

    // With the anchor gone, a fresh shift-click should behave like a single
    // toggle, not extend from the cleared anchor.
    fireEvent.click(checkboxFor('D'), { shiftKey: true })
    expect(selectedTitles()).toEqual(['D'])
  })
})

describe('ChatSidebar project grouping', () => {
  const projects = [
    { id: 'p1', name: 'Alpha Project', conversation_count: 2 },
    { id: 'p2', name: 'Beta Project', conversation_count: 0 },
  ]
  const convs = [
    { id: 'A', title: 'A', parent_conversation_id: null, project_id: 'p1', updated_at: '2026-01-01' },
    { id: 'A1', title: 'A1', parent_conversation_id: 'A', project_id: null, updated_at: '2026-01-01' },
    { id: 'B', title: 'B', parent_conversation_id: null, project_id: 'p1', updated_at: '2026-01-01' },
    { id: 'C', title: 'C', parent_conversation_id: null, project_id: null, updated_at: '2026-01-01' },
    { id: 'D', title: 'D', parent_conversation_id: null, project_id: 'gone', updated_at: '2026-01-01' },
  ]

  function renderWithProjects(overrides = {}) {
    return render(
      <ChatSidebar
        conversations={convs}
        activeId={null}
        onSelect={() => {}}
        onCreate={() => {}}
        onDelete={() => {}}
        onDeleteMany={() => {}}
        projects={projects}
        onCreateProject={() => {}}
        onRenameProject={() => {}}
        onDeleteProject={() => {}}
        onCreateInProject={() => {}}
        onMoveMany={() => {}}
        collapsed={false}
        onCollapse={() => {}}
        onExpand={() => {}}
        {...overrides}
      />
    )
  }

  it('renders project headers with their conversations grouped under them', () => {
    renderWithProjects()
    expect(screen.getByText('Alpha Project')).toBeTruthy()
    expect(screen.getByText('Beta Project')).toBeTruthy()
    // A (and its spinoff A1) and B are under Alpha; C is unfiled.
    expect(screen.getByText('A')).toBeTruthy()
    expect(screen.getByText('A1')).toBeTruthy()
    expect(screen.getByText('C')).toBeTruthy()
  })

  it('a conversation pointing at an unknown project renders as unfiled', () => {
    renderWithProjects()
    expect(screen.getByText('D')).toBeTruthy()
  })

  it('an empty project shows an empty placeholder', () => {
    renderWithProjects()
    expect(screen.getByText('Empty project')).toBeTruthy()
  })

  it('a project whose conversations are not loaded is never claimed empty', () => {
    // Server says 3 conversations, but none made it into the loaded list —
    // show a "not loaded" placeholder (and the authoritative count), not
    // "Empty project".
    render(
      <ChatSidebar
        conversations={[]}
        activeId={null}
        onSelect={() => {}}
        onCreate={() => {}}
        onDelete={() => {}}
        onDeleteMany={() => {}}
        projects={[{ id: 'p9', name: 'Ghost', conversation_count: 3 }]}
        collapsed={false}
        onCollapse={() => {}}
        onExpand={() => {}}
      />
    )
    expect(screen.queryByText('Empty project')).toBeNull()
    expect(screen.getByText('3 conversations not loaded')).toBeTruthy()
    expect(within(screen.getByTestId('project-header-p9')).getByText('3')).toBeTruthy()
  })

  it('collapsing a project hides its conversations', () => {
    renderWithProjects()
    fireEvent.click(screen.getByTestId('project-header-p1'))
    expect(screen.queryByText('A')).toBeNull()
    expect(screen.queryByText('A1')).toBeNull()
    expect(screen.queryByText('B')).toBeNull()
    // Unfiled conversations stay visible.
    expect(screen.getByText('C')).toBeTruthy()
    // Expanding brings them back.
    fireEvent.click(screen.getByTestId('project-header-p1'))
    expect(screen.getByText('A')).toBeTruthy()
  })

  it('spinoffs render under their parent inside the project regardless of own project_id', () => {
    renderWithProjects()
    // A1 has project_id null but its parent A is in p1 — it must render
    // (under A), not be duplicated in the unfiled section.
    expect(screen.getAllByText('A1')).toHaveLength(1)
  })

  it('shift-click range never crosses into a collapsed project', () => {
    renderWithProjects()
    // Collapse Alpha (A, A1, B hidden). Anchor on C, shift-click D:
    // range must be just C..D — no hidden rows selected.
    fireEvent.click(screen.getByTestId('project-header-p1'))
    fireEvent.click(checkboxFor('C'))
    fireEvent.click(checkboxFor('D'), { shiftKey: true })
    // Expand and verify hidden rows were not swept into the selection.
    fireEvent.click(screen.getByTestId('project-header-p1'))
    expect(selectedTitles()).toEqual(['C', 'D'])
  })

  it('selection toolbar offers Move to… with each project and No project', () => {
    renderWithProjects()
    fireEvent.click(checkboxFor('C'))
    const select = screen.getByTitle('Move selected to project')
    const options = within(select).getAllByRole('option').map(o => o.textContent)
    expect(options).toEqual(['Move to…', 'Alpha Project', 'Beta Project', 'No project'])
  })

  it('choosing a project in Move to… calls onMoveMany with ids and project id', () => {
    const onMoveMany = vi.fn()
    renderWithProjects({ onMoveMany })
    fireEvent.click(checkboxFor('C'))
    fireEvent.change(screen.getByTitle('Move selected to project'), { target: { value: 'p2' } })
    expect(onMoveMany).toHaveBeenCalledWith(['C'], 'p2')
  })

  it('choosing No project calls onMoveMany with null', () => {
    const onMoveMany = vi.fn()
    renderWithProjects({ onMoveMany })
    fireEvent.click(checkboxFor('A'))
    fireEvent.change(screen.getByTitle('Move selected to project'), { target: { value: '__none__' } })
    expect(onMoveMany).toHaveBeenCalledWith(['A'], null)
  })

  it('moving a selected spinoff resolves to its root (membership is root-only)', () => {
    const onMoveMany = vi.fn()
    renderWithProjects({ onMoveMany })
    fireEvent.click(checkboxFor('A1'))
    fireEvent.change(screen.getByTitle('Move selected to project'), { target: { value: 'p2' } })
    expect(onMoveMany).toHaveBeenCalledWith(['A'], 'p2')
  })

  it('selecting a root and its spinoff moves the root once (deduped)', () => {
    const onMoveMany = vi.fn()
    renderWithProjects({ onMoveMany })
    fireEvent.click(checkboxFor('A'))
    fireEvent.click(checkboxFor('A1'))
    fireEvent.change(screen.getByTitle('Move selected to project'), { target: { value: 'p2' } })
    expect(onMoveMany).toHaveBeenCalledWith(['A'], 'p2')
  })

  it('project delete asks for confirmation then calls onDeleteProject', () => {
    const onDeleteProject = vi.fn()
    renderWithProjects({ onDeleteProject })
    const header = screen.getByTestId('project-header-p1')
    fireEvent.click(within(header).getByLabelText('Delete project'))
    fireEvent.click(within(header).getByText('Yes'))
    expect(onDeleteProject).toHaveBeenCalledWith('p1')
  })

  it('new-conversation-in-project button calls onCreateInProject without toggling collapse', () => {
    const onCreateInProject = vi.fn()
    renderWithProjects({ onCreateInProject })
    const header = screen.getByTestId('project-header-p2')
    fireEvent.click(within(header).getByLabelText('New conversation in project'))
    expect(onCreateInProject).toHaveBeenCalledWith('p2')
    // Beta stayed expanded (its placeholder is still visible).
    expect(screen.getByText('Empty project')).toBeTruthy()
  })

  it('without projects the sidebar renders the flat list as before', () => {
    render(
      <ChatSidebar
        conversations={convs}
        activeId={null}
        onSelect={() => {}}
        onCreate={() => {}}
        onDelete={() => {}}
        onDeleteMany={() => {}}
        collapsed={false}
        onCollapse={() => {}}
        onExpand={() => {}}
      />
    )
    for (const t of ['A', 'A1', 'B', 'C', 'D']) {
      expect(screen.getByText(t)).toBeTruthy()
    }
    expect(screen.queryByText('Alpha Project')).toBeNull()
  })
})

describe('ChatSidebar active-run indicator', () => {
  function renderWith(convs) {
    return render(
      <ChatSidebar
        conversations={convs}
        activeId={null}
        onSelect={() => {}}
        onCreate={() => {}}
        onDelete={() => {}}
        onDeleteMany={() => {}}
        collapsed={false}
        onCollapse={() => {}}
        onExpand={() => {}}
      />
    )
  }

  function indicatorFor(title) {
    const row = screen.getByText(title).closest('.group')
    return within(row).queryByTestId('active-run-indicator')
  }

  it('shows a running indicator when a conversation has a running active_run', () => {
    renderWith([
      { id: 'A', title: 'A', parent_conversation_id: null, updated_at: '2026-01-01', active_run: { status: 'running' } },
    ])
    const badge = indicatorFor('A')
    expect(badge).not.toBeNull()
    expect(badge.getAttribute('aria-label')).toBe('Run in progress')
  })

  it('shows a queued indicator when a conversation has a queued active_run', () => {
    renderWith([
      { id: 'A', title: 'A', parent_conversation_id: null, updated_at: '2026-01-01', active_run: { status: 'queued' } },
    ])
    const badge = indicatorFor('A')
    expect(badge).not.toBeNull()
    expect(badge.getAttribute('aria-label')).toBe('Run queued')
  })

  it('shows no indicator when active_run is null or terminal', () => {
    renderWith([
      { id: 'A', title: 'A', parent_conversation_id: null, updated_at: '2026-01-01', active_run: null },
      { id: 'B', title: 'B', parent_conversation_id: null, updated_at: '2026-01-01' },
      { id: 'C', title: 'C', parent_conversation_id: null, updated_at: '2026-01-01', active_run: { status: 'completed' } },
    ])
    expect(indicatorFor('A')).toBeNull()
    expect(indicatorFor('B')).toBeNull()
    expect(indicatorFor('C')).toBeNull()
  })
})

describe('ChatSidebar collapse', () => {
  it('calls onCollapse when the hide button is clicked', () => {
    const onCollapse = vi.fn()
    renderSidebar({ onCollapse })
    fireEvent.click(screen.getByLabelText('Hide conversations'))
    expect(onCollapse).toHaveBeenCalled()
  })
})
