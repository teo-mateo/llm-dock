import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeRaw from 'rehype-raw'
import rehypeKatex from 'rehype-katex'
import CopyablePre from './CopyablePre'
import useProseClass from '../../hooks/useProseClass'

const MD_COMPONENTS = {
  pre: CopyablePre,
  a: (props) => {
    const isExternal = props.href && /^https?:\/\//.test(props.href)
    return isExternal ? (
      <a {...props} target="_blank" rel="noopener noreferrer" />
    ) : (
      <a {...props} />
    )
  },
}

export default function ThinkingBlock({ content }) {
  const [open, setOpen] = useState(false)
  const proseClass = useProseClass('prose-xs', 'max-w-none', '[&>*:first-child]:mt-0', '[&>*:last-child]:mb-0')

  if (!content) return null

  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-xs text-fg-subtle hover:text-fg-muted"
      >
        <i className={`fa-solid fa-chevron-${open ? 'down' : 'right'} text-[10px]`}></i>
        <i className="fa-solid fa-brain"></i>
        <span>Thinking ({content.length} chars)</span>
      </button>
      {open && (
        <div className={`mt-1 p-3 bg-surface-muted border border-border rounded text-xs text-fg-muted max-h-60 overflow-auto ${proseClass}`}>
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeKatex]} components={MD_COMPONENTS}>
            {content}
          </ReactMarkdown>
        </div>
      )}
    </div>
  )
}
