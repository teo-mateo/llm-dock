import { Fragment } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import useProseClass from '../../hooks/useProseClass'

function imageLabel(count) {
  return `+${count} image${count === 1 ? '' : 's'}`
}

export default function PiMessage({ item }) {
  const proseClass = useProseClass(
    'prose-sm',
    'max-w-none',
    '[&>*:first-child]:mt-0',
    '[&>*:last-child]:mb-0',
  )

  if (item.kind === 'user') {
    const footer = [
      item.origin === 'extension' ? 'from phone' : null,
      item.imageCount > 0 ? imageLabel(item.imageCount) : null,
    ].filter(Boolean)

    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-xl border border-border bg-surface px-4 py-3">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg">{item.text}</p>
          {footer.length > 0 && (
            <p className="mt-2 text-xs text-fg-muted">
              {footer.map((line, index) => (
                <Fragment key={line}>
                  {index > 0 && ' · '}
                  <span>{line}</span>
                </Fragment>
              ))}
            </p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {item.thinking && (
        <details className="rounded-lg border border-border bg-app px-3 py-2">
          <summary className="cursor-pointer text-xs text-fg-muted">Thinking</summary>
          <div className={`mt-2 text-xs text-fg-muted ${proseClass}`}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.thinking}</ReactMarkdown>
          </div>
        </details>
      )}

      <div className={`text-sm leading-relaxed text-fg ${proseClass}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
      </div>

      {item.streaming && (
        <span aria-label="streaming" className="animate-pulse text-accent">
          ▍
        </span>
      )}

      {item.usage && (
        <output className="text-xs text-fg-muted">{item.usage.output ?? 0} tokens</output>
      )}
    </div>
  )
}
