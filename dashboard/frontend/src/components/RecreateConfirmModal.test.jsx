import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import RecreateConfirmModal from './RecreateConfirmModal'

afterEach(() => cleanup())

function renderModal(props = {}) {
  const onConfirm = props.onConfirm || vi.fn().mockResolvedValue({})
  const onCancel = props.onCancel || vi.fn()
  render(<RecreateConfirmModal running={props.running ?? true} onConfirm={onConfirm} onCancel={onCancel} />)
  return { onConfirm, onCancel }
}

describe('RecreateConfirmModal', () => {
  it('warns about unloading the model for a running service', () => {
    renderModal({ running: true })

    expect(screen.getByTestId('recreate-running-note').textContent).toMatch(/unloaded and reloads from scratch/)
    expect(screen.getByTestId('recreate-running-note').textContent).toMatch(/in-flight requests/i)
    expect(screen.queryByTestId('recreate-stopped-note')).toBeNull()
  })

  it('says a stopped service is created and started', () => {
    renderModal({ running: false })

    expect(screen.getByTestId('recreate-stopped-note').textContent).toMatch(/created and started/)
    expect(screen.queryByTestId('recreate-running-note')).toBeNull()
  })

  it('says what is kept and what is lost', () => {
    renderModal()

    expect(screen.getByRole('dialog').textContent).toMatch(/writable layer is lost/)
    expect(screen.getByRole('dialog').textContent).toMatch(/Bind-mounted/)
  })

  it('cancels from the button, Escape and the backdrop without confirming', () => {
    const { onConfirm, onCancel } = renderModal()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByRole('dialog').parentElement)

    expect(onCancel).toHaveBeenCalledTimes(3)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('clicking inside the dialog does not cancel', () => {
    const { onCancel } = renderModal()

    fireEvent.click(screen.getByRole('dialog'))

    expect(onCancel).not.toHaveBeenCalled()
  })

  it('confirms once and disables both buttons while pending', async () => {
    let resolve
    const onConfirm = vi.fn(() => new Promise(r => { resolve = r }))
    const { onCancel } = renderModal({ onConfirm })

    fireEvent.click(screen.getByRole('button', { name: 'Recreate' }))

    expect(onConfirm).toHaveBeenCalledTimes(1)
    const recreating = await screen.findByRole('button', { name: /Recreating/ })
    expect(recreating.disabled).toBe(true)
    expect(screen.getByRole('button', { name: 'Cancel' }).disabled).toBe(true)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onCancel).not.toHaveBeenCalled()

    resolve({})
  })

  it('shows the Docker error and stays open on failure', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error('failed to bind host port 0.0.0.0:3301/tcp'))
    renderModal({ onConfirm })

    fireEvent.click(screen.getByRole('button', { name: 'Recreate' }))

    expect((await screen.findByRole('alert')).textContent).toBe('failed to bind host port 0.0.0.0:3301/tcp')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Recreate' }).disabled).toBe(false))
    expect(screen.getByRole('dialog')).toBeTruthy()
  })
})
