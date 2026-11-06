import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import PiPromptCard from './PiPromptCard'

afterEach(cleanup)

function prompt(overrides = {}) {
  return {
    prompt_id: 'call-1',
    kind: 'select',
    title: 'Which colour',
    message: 'pi needs a colour before it continues',
    options: ['red', 'green'],
    allow_free_text: false,
    timeout_ms: null,
    ...overrides,
  }
}

function renderCard(overrides = {}, onAnswer = vi.fn().mockResolvedValue({ kind: 'done' })) {
  render(<PiPromptCard prompt={prompt(overrides)} live onAnswer={onAnswer} />)
  return onAnswer
}

describe('PiPromptCard', () => {
  it('shows the question so an operator can answer without the terminal', () => {
    renderCard()
    expect(screen.getByText('pi is asking')).toBeInTheDocument()
    expect(screen.getByText('Which colour')).toBeInTheDocument()
    expect(screen.getByText('pi needs a colour before it continues')).toBeInTheDocument()
  })

  it('answers a confirm with a boolean', async () => {
    const onAnswer = renderCard({ kind: 'confirm', message: '', options: [] })
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }))
    await waitFor(() => expect(onAnswer).toHaveBeenCalledWith(true))
    expect(screen.getByRole('button', { name: 'Yes' })).toBeDisabled()
  })

  it('answers a confirm with false when No is the click that lands', async () => {
    const onAnswer = renderCard({ kind: 'confirm', message: '', options: [] })
    fireEvent.click(screen.getByRole('button', { name: 'No' }))
    await waitFor(() => expect(onAnswer).toHaveBeenCalledWith(false))
  })

  it('answers a select with the option clicked and offers no free text', () => {
    const onAnswer = renderCard()
    expect(screen.getByRole('button', { name: 'red' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'green' })).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/another option/i)).not.toBeInTheDocument()
    expect(screen.getByText(/Pick one of the options/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'green' }))
    expect(onAnswer).toHaveBeenCalledWith('green')
  })

  it('offers free text only when the prompt allows it', () => {
    const onAnswer = renderCard({ allow_free_text: true })
    const field = screen.getByPlaceholderText(/another option/i)
    fireEvent.change(field, { target: { value: 'blue' } })
    fireEvent.click(screen.getByRole('button', { name: 'Answer' }))
    expect(onAnswer).toHaveBeenCalledWith('blue')
  })

  it('accepts a typed answer for an input prompt on Enter', () => {
    const onAnswer = renderCard({ kind: 'input', options: [] })
    expect(screen.getByRole('button', { name: 'Answer' })).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText(/your answer/i), { target: { value: '3301' } })
    fireEvent.submit(screen.getByPlaceholderText(/your answer/i))
    expect(onAnswer).toHaveBeenCalledWith('3301')
  })

  it('sends an approval choice with an optional reason', async () => {
    const onAnswer = renderCard({ kind: 'approval', options: [] })
    expect(screen.getByRole('button', { name: 'Allow once' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Allow for session' })).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText(/reason/i), { target: { value: 'too loud' } })
    fireEvent.click(screen.getByRole('button', { name: 'Deny' }))
    await waitFor(() =>
      expect(onAnswer).toHaveBeenCalledWith({ choice: 'deny', reason: 'too loud' }),
    )
  })

  it('sends an approval with a null reason when none was typed', () => {
    const onAnswer = renderCard({ kind: 'approval', options: [] })
    fireEvent.click(screen.getByRole('button', { name: 'Allow once' }))
    expect(onAnswer).toHaveBeenCalledWith({ choice: 'allow_once', reason: null })
  })

  it('locks the controls while an answer is in flight so one click cannot send twice', async () => {
    let resolveAnswer
    const onAnswer = vi.fn().mockReturnValue(new Promise((done) => { resolveAnswer = done }))
    render(<PiPromptCard prompt={prompt({ kind: 'confirm', options: [] })} live onAnswer={onAnswer} />)
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }))
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }))
    expect(onAnswer).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('status')).toHaveTextContent('Sending')
    resolveAnswer({ kind: 'done' })
    await waitFor(() => expect(screen.queryAllByRole('status')).toHaveLength(0))
  })

  it('keeps the question closed after a 202 and says pi has not accepted it', async () => {
    const onAnswer = vi.fn().mockResolvedValue({
      kind: 'pending', message: 'Sent — pi has not accepted it yet',
    })
    render(<PiPromptCard prompt={prompt({ kind: 'confirm', options: [] })} live onAnswer={onAnswer} />)
    fireEvent.click(screen.getByRole('button', { name: 'Yes' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/not accepted/i))
    expect(screen.getByRole('button', { name: 'Yes' })).toBeDisabled()
    expect(screen.queryByText(/answered/i)).not.toBeInTheDocument()
  })

  it('shows the winning answer when another client got there first', async () => {
    const onAnswer = vi.fn().mockResolvedValue({
      kind: 'closed', message: 'Already answered — green by the terminal',
    })
    render(<PiPromptCard prompt={prompt()} live onAnswer={onAnswer} />)
    fireEvent.click(screen.getByRole('button', { name: 'red' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Already answered — green'))
    expect(screen.getByRole('button', { name: 'red' })).toBeDisabled()
  })

  it('keeps a typed answer when the network fails', async () => {
    const onAnswer = vi.fn().mockRejectedValue(new Error('boom'))
    render(<PiPromptCard prompt={prompt({ kind: 'input', options: [] })} live onAnswer={onAnswer} />)
    const field = screen.getByPlaceholderText(/your answer/i)
    fireEvent.change(field, { target: { value: 'keep me' } })
    fireEvent.submit(field)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/your answer is still here/i))
    expect(field).toHaveValue('keep me')
  })

  it('clears the field once the answer is accepted', async () => {
    const onAnswer = vi.fn().mockResolvedValue({ kind: 'done' })
    render(<PiPromptCard prompt={prompt({ kind: 'input', options: [] })} live onAnswer={onAnswer} />)
    const field = screen.getByPlaceholderText(/your answer/i)
    fireEvent.change(field, { target: { value: '3301' } })
    fireEvent.submit(field)
    await waitFor(() => expect(field).toHaveValue(''))
  })

  it('offers no active control for an offline session', () => {
    render(<PiPromptCard prompt={prompt()} live={false} onAnswer={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'red' })).toBeDisabled()
    expect(screen.getByText(/answer it in the terminal/i)).toBeInTheDocument()
  })
})
