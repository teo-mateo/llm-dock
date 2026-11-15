import { useState } from 'react'
import { cappedSlice } from './lineCap'
import ShowAllToggle from './ShowAllToggle'

const ROW_TONES = {
  hunk: 'text-info-fg',
  add: 'bg-success-subtle text-fg',
  remove: 'bg-danger-subtle text-fg',
  context: 'text-fg',
}

const MARKERS = { add: '+', remove: '-', context: ' ', hunk: '' }

function CodeRow({ line }) {
  const gutter = line.kind === 'hunk' ? '⋯' : (line.number ?? '')
  return (
    <div className={`flex ${ROW_TONES[line.kind] ?? 'text-fg'}`} data-kind={line.kind ?? 'plain'}>
      <span className="w-12 shrink-0 select-none pr-2 text-right text-fg-subtle">{gutter}</span>
      {line.kind != null && <span className="select-none">{MARKERS[line.kind]}</span>}
      <span className="whitespace-pre">{line.text}</span>
    </div>
  )
}

export default function CodeLines({ lines }) {
  const [expanded, setExpanded] = useState(false)
  const { capped, shown } = cappedSlice(lines, expanded)
  return (
    <div className="flex min-w-0 flex-col items-start gap-1">
      <div className="max-h-[32rem] w-full min-w-0 overflow-auto rounded border border-border bg-app py-1 font-mono text-xs">
        <div className="w-max min-w-full">
          {shown.map((line, index) => (
            <CodeRow key={index} line={line} />
          ))}
        </div>
      </div>
      {capped && (
        <ShowAllToggle expanded={expanded} total={lines.length} onToggle={() => setExpanded((value) => !value)} />
      )}
    </div>
  )
}
