import CappedText from './CappedText'

function valueText(value) {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

export default function KeyValueGrid({ entries }) {
  return (
    <dl className="m-0 grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="font-mono text-xs text-fg-subtle">{key}</dt>
          <dd className="m-0 min-w-0">
            <CappedText text={valueText(value)} tone="fg" bare />
          </dd>
        </div>
      ))}
    </dl>
  )
}
