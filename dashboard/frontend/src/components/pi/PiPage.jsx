import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { buildTranscript } from '../../utils/piTranscript'
import { usePiSessionEvents } from '../../hooks/usePiSessionEvents'
import { usePiSessions } from '../../hooks/usePiSessions'
import PiSessionHeader from './PiSessionHeader'
import PiSessionList from './PiSessionList'
import PiTranscript from './PiTranscript'

export default function PiPage() {
  const { sessionId, instanceId } = useParams()
  const navigate = useNavigate()
  const [liveOnly, setLiveOnly] = useState(true)
  const { sessions } = usePiSessions()
  const { events, summary, error } = usePiSessionEvents(sessionId, instanceId)
  const { items, working } = useMemo(() => buildTranscript(events), [events])
  const selectedKey = sessionId && instanceId ? `${sessionId}/${instanceId}` : null

  function handleSelect(session) {
    navigate(`/pi/${session.session_id}/${session.instance_id}`)
  }

  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-stretch min-w-0">
      <aside className="md:w-72 md:flex-none">
        <PiSessionList
          sessions={sessions}
          selectedKey={selectedKey}
          onSelect={handleSelect}
          liveOnly={liveOnly}
          onToggleLiveOnly={setLiveOnly}
        />
      </aside>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col md:h-[calc(100vh-160px)]">
        {!selectedKey ? (
          <p className="text-sm text-fg-muted">Select a session</p>
        ) : error === 'unknown_session' ? (
          <p className="text-sm text-fg-muted">
            This session is no longer known to the dashboard.
          </p>
        ) : (
          <>
            {summary && <PiSessionHeader summary={summary} />}
            <PiTranscript items={items} working={working} />
          </>
        )}
      </section>
    </div>
  )
}
