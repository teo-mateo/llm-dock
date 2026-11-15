import { useState } from 'react'
import { cappedSlice } from './lineCap'
import ChatText from './ChatText'
import ResultMessage from './ResultMessage'
import ShowAllToggle from './ShowAllToggle'
import ToolChip from './ToolChip'
import ToolMeta from './ToolMeta'

function lineFrame(line) {
  if (line.important) return 'border-warning bg-warning-subtle'
  if (line.toYou) return 'border-accent bg-accent-subtle'
  return 'border-transparent'
}

function senderClass(bot) {
  return bot ? 'text-info-fg' : 'text-fg'
}

function ChatLineView({ line }) {
  return (
    <li data-to-you={line.toYou || undefined} className={`flex min-w-0 flex-col gap-0.5 rounded border-l-2 px-2 py-1 ${lineFrame(line)}`}>
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 text-xs">
        {line.time && <span className="font-mono text-fg-muted">{line.time}</span>}
        {line.from && <span className={`font-semibold ${senderClass(line.bot)}`}>{line.from}</span>}
        {line.toYou && <span className="text-fg-muted">to you</span>}
        {line.private && <ToolChip>private</ToolChip>}
        {line.important && <ToolChip tone="warning">important</ToolChip>}
      </div>
      {line.text.trim() !== '' && <ChatText text={line.text} />}
    </li>
  )
}

function ChatLines({ lines }) {
  const [expanded, setExpanded] = useState(false)
  if (lines.length === 0) return <p className="m-0 text-xs text-fg-muted">(no messages)</p>
  const { capped, shown } = cappedSlice(lines, expanded)
  return (
    <div className="flex min-w-0 flex-col items-start gap-1">
      <ul className="m-0 flex w-full min-w-0 list-none flex-col gap-1 p-0">
        {shown.map((line, index) => (
          <ChatLineView key={index} line={line} />
        ))}
      </ul>
      {capped && (
        <ShowAllToggle
          expanded={expanded}
          total={lines.length}
          noun="messages"
          onToggle={() => setExpanded((value) => !value)}
        />
      )}
    </div>
  )
}

function People({ people }) {
  return (
    <ul className="m-0 flex list-none flex-wrap gap-x-3 gap-y-1 p-0 text-sm">
      {people.map((person, index) => (
        <li key={index} className={senderClass(person.bot)}>
          {person.nick}
          {person.bot && <span className="ml-1 text-xs text-fg-muted">bot</span>}
        </li>
      ))}
    </ul>
  )
}

export default function ChatterboxLookBody({ tool }) {
  const { item, view } = tool
  return (
    <>
      <ToolMeta item={item}>
        <span className="font-semibold text-fg">look {view.what ?? 'status'}</span>
      </ToolMeta>
      <ResultMessage tool={tool} when="error" />
      {view.lines != null ? (
        <ChatLines lines={view.lines} />
      ) : view.people != null ? (
        <People people={view.people} />
      ) : (
        <ResultMessage tool={tool} when="ok" />
      )}
    </>
  )
}
