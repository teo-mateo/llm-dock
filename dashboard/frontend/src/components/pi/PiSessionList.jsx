import PageTitle from '../PageTitle'
import { needsAnswer } from '../../utils/piPrompts'

function sessionName(session) {
  if (session.name) return session.name
  const segments = session.cwd.split('/').filter(Boolean)
  return segments.length > 0 ? segments[segments.length - 1] : session.cwd
}

function pathTail(cwd) {
  const segments = cwd.split('/').filter(Boolean)
  return segments.length > 1 ? segments.slice(-2).join('/') : cwd
}

function sessionStatus(session) {
  if (!session.live) return 'ended'
  return session.state || 'idle'
}

function statusDotClass(status) {
  if (status === 'working') return 'bg-warning-fg'
  if (status === 'idle') return 'bg-success-fg'
  return 'bg-fg-muted'
}

function statusTextClass(status) {
  if (status === 'working') return 'text-warning-fg'
  if (status === 'idle') return 'text-success-fg'
  return 'text-fg-muted'
}

export default function PiSessionList({
  sessions,
  selectedKey,
  onSelect,
  liveOnly,
  onToggleLiveOnly,
}) {
  const visible = liveOnly ? sessions.filter((session) => session.live) : sessions

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <PageTitle as="h2">Sessions</PageTitle>
        <label className="flex items-center gap-2 text-xs text-fg-muted">
          <input
            type="checkbox"
            checked={liveOnly}
            onChange={(event) => onToggleLiveOnly(event.target.checked)}
          />
          live only
        </label>
      </div>

      {visible.length === 0 ? (
        <p className="text-sm text-fg-muted">
          No pi sessions yet — start pi with the pi-remote extension.
        </p>
      ) : (
        <ul className="flex flex-col gap-1">
          {visible.map((session) => {
            const key = `${session.session_id}/${session.instance_id}`
            const status = sessionStatus(session)
            const selected = key === selectedKey
            const pending = needsAnswer(session) ? session.prompts.length : 0
            return (
              <li key={key}>
                <button
                  type="button"
                  aria-current={selected ? 'true' : undefined}
                  title={`${sessionName(session)} — ${session.cwd}`}
                  onClick={() => onSelect(session)}
                  className={`flex w-full min-w-0 items-center gap-2 rounded-md border px-2 py-1.5 text-left max-sm:min-h-11 focus-visible:ring-2 focus-visible:ring-accent ${
                    selected
                      ? 'bg-surface border-accent'
                      : 'bg-app border-border hover:bg-surface'
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`h-2 w-2 flex-none rounded-full ${statusDotClass(status)}`}
                  ></span>
                  <span className="min-w-0 flex-1 truncate text-sm font-semibold text-fg">
                    {sessionName(session)}
                  </span>
                  <span className="min-w-0 shrink-[3] truncate font-mono text-xs text-fg-muted block sm:hidden">
                    {pathTail(session.cwd)}
                  </span>
                  {pending > 0 && (
                    <span
                      aria-label={`${pending} question${pending === 1 ? '' : 's'} waiting`}
                      className="flex-none rounded-full border border-accent bg-accent-subtle px-1.5 py-px text-[11px] font-semibold leading-tight text-accent-strong"
                    >
                      {pending} waiting
                    </span>
                  )}
                  <span className={`flex-none text-xs ${statusTextClass(status)}`}>
                    {status}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
