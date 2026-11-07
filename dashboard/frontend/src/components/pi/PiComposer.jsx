import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

// Textarea line boxes are fractional (22.5px at 15px/1.5) and scrollHeight
// rounds them up, so an exact fit raises a scrollbar that eats the slack it
// just measured. Two spare pixels keep a grown composer scroll-free.
const FIT_SLACK_PX = 2

export default function PiComposer({ live, working, onSend, onStop }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [notice, setNotice] = useState(null)
  const boxRef = useRef(null)

  const fit = useCallback(() => {
    const box = boxRef.current
    if (!box) return
    box.style.height = 'auto'
    const borders = box.offsetHeight - box.clientHeight
    box.style.height = `${box.scrollHeight + borders + FIT_SLACK_PX}px`
  }, [])

  useLayoutEffect(fit, [text, live, fit])

  useEffect(() => {
    const onResize = () => fit()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [fit])

  if (!live) {
    return (
      <p className="border-t border-border bg-app px-4 py-3 text-center text-sm text-fg-muted">
        Session ended — read only
      </p>
    )
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
    <div className="shrink-0 border-t border-border bg-app px-4 py-3 md:px-6">
      <div className="mx-auto flex max-w-3xl flex-wrap items-end gap-2">
        <label htmlFor="pi-message" className="sr-only">Message to pi</label>
        <textarea
          ref={boxRef}
          id="pi-message"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder={working ? 'Steer pi… (it is working)' : 'Message pi…'}
          className="min-h-[44px] max-h-[40dvh] min-w-[160px] flex-1 resize-none overflow-y-auto rounded-xl border border-border-strong bg-surface px-3 py-2.5 text-[15px] text-fg placeholder:text-fg-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-subtle"
        />
        {working && (
          <button
            type="button"
            onClick={handleStop}
            disabled={stopping}
            className="h-11 rounded-xl border border-danger bg-danger-subtle px-4 text-sm font-semibold text-danger-fg disabled:opacity-60"
          >
            Stop
          </button>
        )}
        <button
          type="button"
          onClick={handleSend}
          disabled={!canSend}
          className="h-11 rounded-xl bg-accent-strong px-4 text-sm font-semibold text-fg-inverse hover:bg-accent-hover disabled:bg-surface-strong disabled:text-fg-subtle"
        >
          Send
        </button>
      </div>
      {notice && (
        <p role="status" className="mx-auto mt-2 max-w-3xl text-xs text-danger-fg">{notice}</p>
      )}
    </div>
  )
}
