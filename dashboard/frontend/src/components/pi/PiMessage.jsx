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
    '[&_td]:[overflow-wrap:anywhere]',
    '[&_th]:[overflow-wrap:anywhere]',
  )

  if (item.kind === 'user') {
    const footer = [
      item.imageCount > 0 ? imageLabel(item.imageCount) : null,
    ].filter(Boolean)

    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent-strong px-4 py-2.5">
          <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-fg-inverse">{item.text}</p>
          {footer.length > 0 && (
            <p className="mt-1.5 text-xs text-fg-inverse opacity-80">
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

  if (!item.text.trim() && !item.thinking && !item.streaming) return null

  return (
    <div className="flex flex-col gap-2">
      {item.thinking && (
        <details className="group self-start rounded-lg open:w-full open:border open:border-border open:bg-app open:px-3 open:py-2">
          <summary className="cursor-pointer select-none text-xs font-medium text-fg-subtle hover:text-fg-muted">
            Thinking
          </summary>
          <div className={`mt-2 text-xs text-fg-muted ${proseClass}`}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.thinking}</ReactMarkdown>
          </div>
        </details>
      )}

      <div className={`text-[15px] leading-relaxed text-fg ${proseClass}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
      </div>

      {item.streaming && (
        <span aria-label="streaming" className="animate-pulse text-accent">
          ▍
        </span>
      )}
    </div>
  )
}
