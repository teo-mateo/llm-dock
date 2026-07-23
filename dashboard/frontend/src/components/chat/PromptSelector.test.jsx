import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import PromptSelector from './PromptSelector'

afterEach(() => cleanup())

const PROMPTS = [
  { id: 'p-2', name: 'Second', content: 'You are a coding expert.', sort_order: 1 },
  { id: 'p-1', name: 'First', content: 'You are a helpful assistant.', sort_order: 0 },
  { id: 'p-3', name: 'Third', content: 'You are a terse expert.', sort_order: 2 },
]

function expandSelector() {
  fireEvent.click(screen.getByRole('button', { name: /System Prompt/ }))
}

describe('PromptSelector', () => {
  it('is collapsed by default — no radio options visible', () => {
    const { container } = render(
      <PromptSelector prompts={PROMPTS} selectedPromptId={null} onSelect={vi.fn()} />,
    )
    expect(container.querySelector('input[type="radio"]')).toBeNull()
    expect(container.textContent).not.toContain('Select a prompt')
  })

  it('expands to show options when the header is clicked', () => {
    render(<PromptSelector prompts={PROMPTS} selectedPromptId={null} onSelect={vi.fn()} />)
    expandSelector()
    expect(screen.getByText('Select a prompt')).toBeTruthy()
    expect(screen.getAllByRole('radio')).toHaveLength(4)
  })

  it('collapses again when the header is clicked while open', () => {
    const { container } = render(
      <PromptSelector prompts={PROMPTS} selectedPromptId={null} onSelect={vi.fn()} />,
    )
    expandSelector()
    expect(container.querySelector('input[type="radio"]')).toBeTruthy()
    expandSelector()
    expect(container.querySelector('input[type="radio"]')).toBeNull()
  })

  it('renders a None option plus one radio per prompt', () => {
    render(<PromptSelector prompts={PROMPTS} selectedPromptId={null} onSelect={vi.fn()} />)
    expandSelector()
    expect(screen.getAllByRole('radio')).toHaveLength(4)
    expect(screen.getAllByText('None')).toHaveLength(2)
  })

  it('renders prompts sorted by sort_order', () => {
    render(<PromptSelector prompts={PROMPTS} selectedPromptId={null} onSelect={vi.fn()} />)
    expandSelector()
    const labels = screen.getAllByRole('radio').slice(1).map(r => r.closest('label').textContent)
    expect(labels[0]).toContain('First')
    expect(labels[1]).toContain('Second')
    expect(labels[2]).toContain('Third')
  })

  it('calls onSelect(null) when None is clicked', () => {
    const onSelect = vi.fn()
    render(<PromptSelector prompts={PROMPTS} selectedPromptId="p-1" onSelect={onSelect} />)
    expandSelector()
    fireEvent.click(screen.getByRole('radio', { name: /^None/ }))
    expect(onSelect).toHaveBeenCalledWith(null)
    expect(onSelect).toHaveBeenCalledTimes(1)
  })

  it('calls onSelect(promptId) when a prompt radio is clicked', () => {
    const onSelect = vi.fn()
    render(<PromptSelector prompts={PROMPTS} selectedPromptId={null} onSelect={onSelect} />)
    expandSelector()
    fireEvent.click(screen.getByRole('radio', { name: /First/ }))
    expect(onSelect).toHaveBeenCalledWith('p-1')
  })

  it('marks the None option as checked when selectedPromptId is null', () => {
    render(<PromptSelector prompts={PROMPTS} selectedPromptId={null} onSelect={vi.fn()} />)
    expandSelector()
    const radios = screen.getAllByRole('radio')
    expect(radios[0]).toBeChecked()
    expect(radios[1]).not.toBeChecked()
  })

  it('marks the matching prompt as checked', () => {
    render(<PromptSelector prompts={PROMPTS} selectedPromptId="p-2" onSelect={vi.fn()} />)
    expandSelector()
    const radios = screen.getAllByRole('radio')
    expect(radios[0]).not.toBeChecked()
    expect(radios[1]).not.toBeChecked()
    expect(radios[2]).toBeChecked()
  })

  it('shows the selected prompt name in the collapsed button', () => {
    render(<PromptSelector prompts={PROMPTS} selectedPromptId="p-1" onSelect={vi.fn()} />)
    expect(screen.getByRole('button', { name: /System Prompt/ }).textContent).toContain('First')
  })

  it('shows "None" in the collapsed button when nothing is selected', () => {
    render(<PromptSelector prompts={PROMPTS} selectedPromptId={null} onSelect={vi.fn()} />)
    expect(screen.getByRole('button', { name: /System Prompt/ }).textContent).toContain('None')
  })

  it('shows "Custom" in the collapsed button when the selected id is not in the list', () => {
    render(
      <PromptSelector prompts={PROMPTS} selectedPromptId="unknown-id" onSelect={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: /System Prompt/ }).textContent).toContain('Custom')
  })

  it('shows a truncated content preview for the selected prompt', () => {
    const longContent = 'A'.repeat(200)
    const prompts = [{ id: 'p-1', name: 'Long', content: longContent, sort_order: 0 }]
    render(<PromptSelector prompts={prompts} selectedPromptId="p-1" onSelect={vi.fn()} />)
    expandSelector()
    const preview = screen.getByText(/AAA/)
    expect(preview.textContent).toHaveLength(121)
  })

  it('shows full content when it fits within the preview limit', () => {
    const prompts = [
      { id: 'p-1', name: 'Short', content: 'You are a helpful assistant.', sort_order: 0 },
    ]
    render(<PromptSelector prompts={prompts} selectedPromptId="p-1" onSelect={vi.fn()} />)
    expandSelector()
    expect(screen.getByText('You are a helpful assistant.')).toBeTruthy()
  })

  it('renders without crashing when prompts is an empty array', () => {
    render(<PromptSelector prompts={[]} selectedPromptId={null} onSelect={vi.fn()} />)
    expandSelector()
    expect(screen.getAllByRole('radio')).toHaveLength(1)
    expect(screen.getAllByText('None')).toHaveLength(2)
  })

  it('renders without crashing when prompts is undefined', () => {
    render(<PromptSelector prompts={undefined} selectedPromptId={null} onSelect={vi.fn()} />)
    expandSelector()
    expect(screen.getAllByRole('radio')).toHaveLength(1)
  })

  it('handles prompts with empty content', () => {
    const prompts = [{ id: 'p-1', name: 'Empty', content: '', sort_order: 0 }]
    render(<PromptSelector prompts={prompts} selectedPromptId="p-1" onSelect={vi.fn()} />)
    expandSelector()
    expect(screen.getAllByText('Empty')).toHaveLength(2)
  })

  it('uses a custom label when provided', () => {
    render(
      <PromptSelector
        prompts={PROMPTS}
        selectedPromptId={null}
        onSelect={vi.fn()}
        label="Sidekick Prompt"
      />,
    )
    expect(screen.getByRole('button', { name: /Sidekick Prompt/ })).toBeTruthy()
  })

  it('shows the "applies to this conversation only" note when expanded', () => {
    render(<PromptSelector prompts={PROMPTS} selectedPromptId={null} onSelect={vi.fn()} />)
    expandSelector()
    expect(screen.getByText(/Selection applies to this conversation only/)).toBeTruthy()
  })

  it('does not show the note when collapsed', () => {
    render(<PromptSelector prompts={PROMPTS} selectedPromptId={null} onSelect={vi.fn()} />)
    expect(screen.queryByText(/Selection applies to this conversation only/)).toBeNull()
  })
})
