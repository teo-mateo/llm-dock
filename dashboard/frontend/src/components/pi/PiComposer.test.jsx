import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import PiComposer from './PiComposer'

afterEach(cleanup)

function renderComposer(props = {}) {
  render(
    <PiComposer
      live
      working={false}
      onSend={vi.fn()}
      onStop={vi.fn()}
      {...props}
    />,
  )
}

describe('PiComposer', () => {
  it('enter sends and clears on done', async () => {
    const onSend = vi.fn().mockResolvedValue({ kind: 'done', message: null })
    renderComposer({ onSend })
    const textarea = screen.getByLabelText('Message to pi')
    fireEvent.change(textarea, { target: { value: 'hello' } })
    fireEvent.keyDown(textarea, { key: 'Enter' })
    await waitFor(() => expect(onSend).toHaveBeenCalledWith('hello'))
    await waitFor(() => expect(textarea).toHaveValue(''))
  })

  it('shift enter adds a newline', () => {
    const onSend = vi.fn()
    renderComposer({ onSend })
    const textarea = screen.getByLabelText('Message to pi')
    fireEvent.change(textarea, { target: { value: 'hello' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true })
    expect(textarea).toHaveValue('hello\n')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('whitespace cannot be sent', () => {
    const onSend = vi.fn()
    renderComposer({ onSend })
    const textarea = screen.getByLabelText('Message to pi')
    fireEvent.change(textarea, { target: { value: '   ' } })
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    fireEvent.keyDown(textarea, { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
  })

  it('stop shown only while working', () => {
    renderComposer({ working: false })
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument()
    cleanup()
    renderComposer({ working: true })
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()
  })

  it('rejected keeps text and shows message', async () => {
    const onSend = vi.fn().mockResolvedValue({
      kind: 'rejected',
      message: 'pi is offline',
    })
    renderComposer({ onSend })
    const textarea = screen.getByLabelText('Message to pi')
    fireEvent.change(textarea, { target: { value: 'hello' } })
    fireEvent.keyDown(textarea, { key: 'Enter' })
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('pi is offline'))
    expect(textarea).toHaveValue('hello')
  })

  it('ended session is read only', () => {
    renderComposer({ live: false })
    expect(screen.getByText('Session ended — read only')).toBeInTheDocument()
    expect(screen.queryByLabelText('Message to pi')).not.toBeInTheDocument()
  })

  it('placeholder says steer while working', () => {
    renderComposer({ working: true })
    expect(screen.getByLabelText('Message to pi')).toHaveAttribute(
      'placeholder',
      'Steer pi… (it is working)',
    )
  })
})
