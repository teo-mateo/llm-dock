import { useState } from 'react'

const CONFIRM_YES = 'Yes'
const CONFIRM_NO = 'No'
const APPROVALS = [
  ['allow_once', 'Allow once'],
  ['allow_session', 'Allow for session'],
  ['deny', 'Deny'],
]

function buttonClass(primary) {
  return primary
    ? 'h-10 rounded-xl bg-accent-strong px-4 text-sm font-semibold text-fg-inverse hover:bg-accent-hover disabled:bg-surface-strong disabled:text-fg-subtle'
    : 'h-10 rounded-xl border border-border-strong bg-surface px-4 text-sm font-semibold text-fg hover:border-accent disabled:opacity-60'
}

function fieldClass() {
  return 'min-w-[140px] flex-1 rounded-xl border border-border-strong bg-surface px-3 py-2 text-[15px] text-fg placeholder:text-fg-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-subtle'
}

export default function PiPromptCard({ prompt, live, onAnswer }) {
  const [text, setText] = useState('')
  const [reason, setReason] = useState('')
  const [sending, setSending] = useState(false)
  const [notice, setNotice] = useState(null)
  const [settled, setSettled] = useState(false)

  const disabled = !live || settled || sending
  const kind = prompt.kind

  async function submit(value) {
    if (disabled) return
    setSending(true)
    try {
      const outcome = await onAnswer(value)
      if (outcome.kind === 'done') {
        setNotice(null)
        setSettled(true)
      } else {
        setNotice({ kind: outcome.kind, message: outcome.message })
        if (outcome.kind === 'closed' || outcome.kind === 'pending') setSettled(true)
      }
      if (outcome.kind === 'done' || outcome.kind === 'pending') {
        setText('')
        setReason('')
      }
    } catch {
      setNotice({ kind: 'rejected', message: 'Could not reach the dashboard — your answer is still here' })
    } finally {
      setSending(false)
    }
  }

  function submitText() {
    if (!text.trim()) return
    submit(text.trim())
  }

  function submitApproval(choice) {
    submit({ choice, reason: reason.trim() ? reason.trim() : null })
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (kind === 'input' || prompt.allow_free_text) submitText()
      }}
      className="border-b border-accent-subtle bg-surface px-4 py-3 md:px-6"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="rounded-full border border-accent bg-accent-subtle px-2 py-0.5 text-xs font-semibold text-accent-strong">
            pi is asking
          </span>
          <p className="min-w-0 flex-1 text-sm font-semibold text-fg">{prompt.title}</p>
        </div>

        {prompt.message && (
          <p className="whitespace-pre-line text-sm text-fg-muted">{prompt.message}</p>
        )}

        {!live && (
          <p className="text-xs text-fg-muted">Session ended — answer it in the terminal.</p>
        )}

        {kind === 'confirm' && (
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={disabled} className={buttonClass(true)} onClick={() => submit(true)}>
              {CONFIRM_YES}
            </button>
            <button type="button" disabled={disabled} className={buttonClass(false)} onClick={() => submit(false)}>
              {CONFIRM_NO}
            </button>
          </div>
        )}

        {(kind === 'select' || kind === 'input') && (
          <div className="flex flex-wrap items-center gap-2">
            {kind === 'select' && (prompt.options || []).map((option) => (
              <button
                key={option}
                type="button"
                disabled={disabled}
                className={buttonClass(false)}
                onClick={() => submit(option)}
              >
                {option}
              </button>
            ))}
            {kind === 'input' || prompt.allow_free_text ? (
              <>
                <label htmlFor={`pi-prompt-${prompt.prompt_id}`} className="sr-only">
                  {kind === 'select' ? 'Another option' : 'Your answer'}
                </label>
                <input
                  id={`pi-prompt-${prompt.prompt_id}`}
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder={kind === 'select' ? 'Type another option…' : 'Your answer…'}
                  className={fieldClass()}
                  disabled={disabled}
                />
                <button type="submit" disabled={disabled || !text.trim()} className={buttonClass(true)}>
                  Answer
                </button>
              </>
            ) : (
              <span className="text-xs text-fg-subtle">Pick one of the options above.</span>
            )}
          </div>
        )}

        {kind === 'approval' && (
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor={`pi-prompt-reason-${prompt.prompt_id}`} className="sr-only">
              Reason
            </label>
            <input
              id={`pi-prompt-reason-${prompt.prompt_id}`}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Reason (optional)"
              className={fieldClass()}
              disabled={disabled}
            />
            {APPROVALS.map(([choice, label]) => (
              <button
                key={choice}
                type="button"
                disabled={disabled}
                className={buttonClass(choice === 'allow_once')}
                onClick={() => submitApproval(choice)}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {sending && (
          <p role="status" className="text-xs text-fg-muted">Sending…</p>
        )}
        {!sending && notice && (
          <p
            role="status"
            className={`text-xs ${notice.kind === 'pending' ? 'text-fg-muted' : 'text-danger-fg'}`}
          >
            {notice.message}
          </p>
        )}
      </div>
    </form>
  )
}
