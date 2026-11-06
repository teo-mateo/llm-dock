import { useState } from 'react'

export default function PiComposer({ live, working, onSend, onStop }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [notice, setNotice] = useState(null)

  if (!live) {
    return <p className="text-sm text-fg-muted">Session ended — read only</p>
  }

  async function handleSend() {
    if (!text.trim() || sending) return
    setSending(true)
    try {
      const outcome = await onSend(text)
      if (outcome.kind === 'done' || outcome.kind === 'pending') {
        setText('')
        setNotice(null)
      } else {
        setNotice(outcome.message)
      }
    } catch {
      setNotice('Could not send')
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(event) {
    if (event.key !== 'Enter') return
    if (event.shiftKey) {
      event.preventDefault()
      const start = event.currentTarget.selectionStart ?? text.length
      const end = event.currentTarget.selectionEnd ?? text.length
      setText(`${text.slice(0, start)}\n${text.slice(end)}`)
      return
    }
    event.preventDefault()
    handleSend()
  }

  async function handleStop() {
    if (stopping) return
    setStopping(true)
    try {
      await onStop()
    } catch {
      setStopping(false)
    } finally {
      setStopping(false)
    }
  }

  const canSend = text.trim().length > 0 && !sending

  return (
    <div className="border-t border-border pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="pi-message" className="sr-only">Message to pi</label>
        <textarea
          id="pi-message"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder={working ? 'Steer pi… (it is working)' : 'Message pi…'}
          className="min-h-[44px] min-w-[160px] flex-1 resize-none rounded-lg border border-border bg-surface px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:border-accent focus:outline-none"
        />
        {working && (
          <button
            type="button"
            onClick={handleStop}
            disabled={stopping}
            className="h-11 rounded-lg border border-danger bg-danger-subtle px-4 text-sm font-semibold text-danger-fg disabled:opacity-60"
          >
            Stop
          </button>
        )}
        <button
          type="button"
          onClick={handleSend}
          disabled={!canSend}
          className="h-11 rounded-lg bg-accent-strong px-4 text-sm font-semibold text-fg-inverse hover:bg-accent-hover disabled:bg-surface-strong disabled:text-fg-subtle"
        >
          Send
        </button>
      </div>
      {notice && (
        <p role="status" className="mt-2 text-xs text-danger-fg">{notice}</p>
      )}
    </div>
  )
}
