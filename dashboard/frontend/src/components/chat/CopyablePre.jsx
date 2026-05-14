import { useState, Children, isValidElement } from 'react'

function extractText(node) {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (isValidElement(node)) return extractText(node.props.children)
  return ''
}

export default function CopyablePre({ children, ...rest }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = (e) => {
    e.stopPropagation()
    const codeNode = Children.toArray(children).find(isValidElement)
    const text = extractText(codeNode || children)
    if (!text) return
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }).catch(() => { /* ignore */ })
  }

  return (
    <div className="group/code relative my-2">
      <button
        type="button"
        onClick={handleCopy}
        className="absolute top-1.5 right-1.5 z-10 px-2 py-1 text-[10px] font-medium rounded bg-gray-700/80 text-gray-300 hover:bg-gray-600 hover:text-white opacity-0 group-hover/code:opacity-100 focus:opacity-100 transition-opacity"
        title={copied ? 'Copied' : 'Copy code'}
        aria-label={copied ? 'Code copied' : 'Copy code'}
      >
        {copied ? (
          <><i className="fa-solid fa-check mr-1"></i>Copied</>
        ) : (
          <><i className="fa-solid fa-copy mr-1"></i>Copy</>
        )}
      </button>
      <pre {...rest}>{children}</pre>
    </div>
  )
}
