import './PiPage.css'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { buildTranscript } from '../../utils/piTranscript'
import { commandOutcome } from '../../utils/piCommands'
import { promptOutcome } from '../../utils/piPrompts'
import { usePiSessionEvents } from '../../hooks/usePiSessionEvents'
import { usePiSessions } from '../../hooks/usePiSessions'
import { abortPiRun, answerPiPrompt, sendPiMessage } from '../../services/piRemote'
import PiComposer from './PiComposer'
import PiPromptCard from './PiPromptCard'
import PiSessionHeader from './PiSessionHeader'
import PiSessionList from './PiSessionList'
import PiTranscript from './PiTranscript'

export default function PiPage() {
  const { sessionId, instanceId } = useParams()
  const navigate = useNavigate()
  const [liveOnly, setLiveOnly] = useState(true)
  const [lastStop, setLastStop] = useState({ key: null, at: null })
  const { sessions } = usePiSessions()
  const { events, summary, error } = usePiSessionEvents(sessionId, instanceId)
  const { items, working } = useMemo(() => buildTranscript(events), [events])
  const prompts = summary?.prompts ?? []
  const selectedKey = sessionId && instanceId ? `${sessionId}/${instanceId}` : null
  const lastStopAt = lastStop.key === selectedKey ? lastStop.at : null

  function handleSelect(session) {
    navigate(`/pi/${session.session_id}/${session.instance_id}`)
  }

  async function handleSend(text) {
    const { status, body } = await sendPiMessage(sessionId, instanceId, text)
    return commandOutcome(status, body)
  }

  async function handleStop() {
    setLastStop({ key: selectedKey, at: Date.now() })
    await abortPiRun(sessionId, instanceId)
  }

  async function handleAnswer(promptId, value) {
    const { status, body } = await answerPiPrompt(sessionId, instanceId, promptId, value)
    return promptOutcome(status, body)
  }

  return (
    <div className="flex w-full min-w-0 flex-col gap-3 md:flex-row md:items-start">
      <aside className={`md:w-60 md:flex-none ${selectedKey ? 'hidden md:block' : ''}`}>
        <PiSessionList
          sessions={sessions}
          selectedKey={selectedKey}
          onSelect={handleSelect}
          liveOnly={liveOnly}
          onToggleLiveOnly={setLiveOnly}
        />
      </aside>

      <section
        className={`pi-canvas min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-surface h-[calc(100dvh-5.5rem)] md:h-[calc(100vh-160px)] ${
          selectedKey ? 'flex' : 'hidden md:flex'
        }`}
      >
        {!selectedKey ? (
          <div className="pi-empty m-auto flex max-w-[calc(100%_-_2rem)] flex-col items-center gap-4 rounded-2xl border border-border px-8 py-7 text-center">
            <span aria-hidden="true" className="pi-empty-mark flex h-12 w-12 items-center justify-center rounded-2xl font-mono text-2xl">✳</span>
            <p className="text-sm text-fg-muted">Pick a session to watch it here.</p>
          </div>
        ) : error === 'unknown_session' ? (
          <p className="m-auto px-6 text-center text-sm text-fg-muted">
            This session is no longer known to the dashboard.
          </p>
        ) : (
          <>
            {summary && <PiSessionHeader summary={summary} onBack={() => navigate('/pi')} />}
            {prompts.length > 0 && (
              <div
                data-testid="pi-prompt-stack"
                aria-label={`${prompts.length} open question${prompts.length === 1 ? '' : 's'}`}
                className="max-h-[45dvh] shrink-0 overflow-y-auto border-b border-border bg-app"
              >
                {prompts.length > 1 && (
                  <p className="sticky top-0 z-10 border-b border-border bg-app px-4 py-1.5 text-xs font-semibold text-fg-muted md:px-6">
                    {prompts.length} questions need an answer
                  </p>
                )}
                {prompts.map((prompt) => (
                  <PiPromptCard
                    key={prompt.prompt_id}
                    prompt={prompt}
                    live={summary?.live}
                    onAnswer={(value) => handleAnswer(prompt.prompt_id, value)}
                  />
                ))}
              </div>
            )}
            <PiTranscript
              items={items}
              working={working}
              lastStopAt={lastStopAt}
            />
            {summary && (
              <PiComposer
                live={summary.live}
                working={working}
                onSend={handleSend}
                onStop={handleStop}
              />
            )}
          </>
        )}
      </section>
    </div>
  )
}
