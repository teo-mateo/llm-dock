import { needsAnswer } from '../../utils/piPrompts'

function sessionName(session) {
  if (session.name) return session.name
  const segments = session.cwd.split('/').filter(Boolean)
  return segments.length > 0 ? segments[segments.length - 1] : session.cwd
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
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-fg">Sessions</h2>
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
        <ul className="flex flex-col gap-2">
          {visible.map((session) => {
            const key = `${session.session_id}/${session.instance_id}`
            const status = sessionStatus(session)
            const selected = key === selectedKey
            return (
              <li key={key}>
                <button
                  type="button"
                  aria-current={selected ? 'true' : undefined}
                  onClick={() => onSelect(session)}
                  className={`w-full rounded-lg border p-3 text-left ${
                    selected
                      ? 'bg-surface border-accent'
                      : 'bg-app border-border hover:bg-surface'
                  }`}
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <span
                      aria-hidden="true"
                      className={`h-2 w-2 flex-none rounded-full ${statusDotClass(status)}`}
                    ></span>
                    <span className="flex-1 min-w-0 truncate text-sm font-semibold text-fg">
                      {sessionName(session)}
                    </span>
                    <span className={`flex-none text-xs ${statusTextClass(status)}`}>
                      {status}
                    </span>
                  </span>
                  {needsAnswer(session) && (
                    <span className="mt-1 flex items-center gap-2">
                      <span className="rounded-full border border-accent bg-accent-subtle px-2 py-0.5 text-xs font-semibold text-accent-strong">
                        {session.prompts.length === 1
                          ? '1 question waiting'
                          : `${session.prompts.length} questions waiting`}
                      </span>
                    </span>
                  )}
                  <span className="mt-1 block truncate font-mono text-xs text-fg-muted">
                    {session.cwd}
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
