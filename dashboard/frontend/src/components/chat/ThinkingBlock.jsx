import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeRaw from 'rehype-raw'
import rehypeKatex from 'rehype-katex'

export default function ThinkingBlock({ content }) {
  const [open, setOpen] = useState(false)

  if (!content) return null

  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-400"
      >
        <i className={`fa-solid fa-chevron-${open ? 'down' : 'right'} text-[10px]`}></i>
        <i className="fa-solid fa-brain"></i>
        <span>Thinking ({content.length} chars)</span>
      </button>
      {open && (
        <div className="mt-1 p-3 bg-gray-900/50 border border-gray-700 rounded text-xs text-gray-400 max-h-60 overflow-auto prose prose-invert prose-xs max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeKatex]}>
            {content}
          </ReactMarkdown>
        </div>
      )}
    </div>
  )
}
