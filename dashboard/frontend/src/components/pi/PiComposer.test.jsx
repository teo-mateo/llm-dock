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

function measureAsTextarea(textarea, wrap = { value: 1 }) {
  const content = () => {
    const lines = textarea.value ? textarea.value.split('\n').length : 1
    return lines * wrap.value * 20 + 20
  }
  Object.defineProperty(textarea, 'scrollHeight', { configurable: true, get: content })
  Object.defineProperty(textarea, 'offsetHeight', { configurable: true, get: () => content() + 4 })
  Object.defineProperty(textarea, 'clientHeight', { configurable: true, get: content })
  return wrap
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

  it('grows to the height of several lines', () => {
    renderComposer()
    const textarea = screen.getByLabelText('Message to pi')
    measureAsTextarea(textarea)
    fireEvent.change(textarea, { target: { value: 'one line' } })
    expect(textarea.style.height).toBe('46px')
    fireEvent.change(textarea, { target: { value: 'one\ntwo\nthree\nfour\nfive' } })
    expect(textarea.style.height).toBe('126px')
  })

  it('shrinks again when the lines are taken back out', () => {
    renderComposer()
    const textarea = screen.getByLabelText('Message to pi')
    measureAsTextarea(textarea)
    fireEvent.change(textarea, { target: { value: 'a\nb\nc\nd\ne\nf' } })
    expect(textarea.style.height).toBe('146px')
    fireEvent.change(textarea, { target: { value: 'a' } })
    expect(textarea.style.height).toBe('46px')
  })

  it('gives the height back after a sent message and keeps it after a rejected one', async () => {
    const done = vi.fn().mockResolvedValue({ kind: 'done', message: null })
    renderComposer({ onSend: done })
    const textarea = screen.getByLabelText('Message to pi')
    measureAsTextarea(textarea)
    fireEvent.change(textarea, { target: { value: 'x\ny\nz' } })
    expect(textarea.style.height).toBe('86px')
    fireEvent.keyDown(textarea, { key: 'Enter' })
    await waitFor(() => expect(textarea).toHaveValue(''))
    await waitFor(() => expect(textarea.style.height).toBe('46px'))

    cleanup()
    const rejected = vi.fn().mockResolvedValue({ kind: 'rejected', message: 'pi is offline' })
    renderComposer({ onSend: rejected })
    const kept = screen.getByLabelText('Message to pi')
    measureAsTextarea(kept)
    fireEvent.change(kept, { target: { value: 'x\ny\nz' } })
    fireEvent.keyDown(kept, { key: 'Enter' })
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('pi is offline'))
    expect(kept).toHaveValue('x\ny\nz')
    expect(kept.style.height).toBe('86px')
  })

  it('bounds the growth with internal scrolling and refits on resize', () => {
    renderComposer()
    const textarea = screen.getByLabelText('Message to pi')
    expect(textarea).toHaveClass('max-h-[40dvh]')
    expect(textarea).toHaveClass('overflow-y-auto')
    expect(textarea).not.toHaveClass('resize-y')
    const wrap = measureAsTextarea(textarea)
    fireEvent.change(textarea, { target: { value: 'a\nb' } })
    expect(textarea.style.height).toBe('66px')
    wrap.value = 4
    window.dispatchEvent(new Event('resize'))
    expect(textarea.style.height).toBe('186px')
  })
})
