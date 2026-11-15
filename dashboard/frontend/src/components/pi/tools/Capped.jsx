import { useState } from 'react'
import { cappedSlice } from './lineCap'
import ShowAllToggle from './ShowAllToggle'

export default function Capped({ items, noun, children }) {
  const [expanded, setExpanded] = useState(false)
  const { capped, shown } = cappedSlice(items, expanded)
  return (
    <div className="flex min-w-0 flex-col items-start gap-1">
      {children(shown)}
      {capped && (
        <ShowAllToggle
          expanded={expanded}
          total={items.length}
          noun={noun}
          onToggle={() => setExpanded((value) => !value)}
        />
      )}
    </div>
  )
}
