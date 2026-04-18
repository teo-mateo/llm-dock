import { useState, useRef, useEffect } from 'react'

export default function ChatInput({ onSend, disabled, pendingInserts = [], onClearInsert }) {
  const [value, setValue] = useState('')
  const [images, setImages] = useState([]) // [{dataUrl, name, size}]
  const textareaRef = useRef(null)

  useEffect(() => {
    if (!disabled && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [disabled])

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current
    if (ta) {
      ta.style.height = 'auto'
      ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
    }
  }, [value])

  function handlePaste(e) {
    const items = e.clipboardData?.items
    if (!items) return

    for (const item of items) {
      if (item.type.startsWith('image/')) {
        e.preventDefault()
        const file = item.getAsFile()
        if (!file) continue
        const reader = new FileReader()
        reader.onload = () => {
          setImages(prev => [...prev, {
            dataUrl: reader.result,
            name: file.name || 'pasted-image',
            size: file.size,
          }])
        }
        reader.readAsDataURL(file)
      }
    }
  }

  function removeImage(idx) {
    setImages(prev => prev.filter((_, i) => i !== idx))
  }

  function buildMessage() {
    let msg = value.trim()
    if (pendingInserts.length > 0) {
      const issueLines = pendingInserts.map((ann) =>
        `- "${ann.span_text}": ${ann.comment}`
      ).join('\n')
      const prefix = `The following issues were identified by a reviewer:\n${issueLines}\n\nPlease address these issues.`
      msg = msg ? `${prefix}\n\n${msg}` : prefix
    }
    return msg
  }

  function handleSubmit(e) {
    e.preventDefault()
    const msg = buildMessage()
    const imgDataUrls = images.map(i => i.dataUrl)
    if ((!msg && imgDataUrls.length === 0) || disabled) return
    onSend(msg, imgDataUrls.length > 0 ? imgDataUrls : undefined)
    setValue('')
    setImages([])
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const canSend = !disabled && (value.trim() || images.length > 0 || pendingInserts.length > 0)

  return (
    <div className="border-t border-gray-700">
      {/* Pending inserts */}
      {pendingInserts.length > 0 && (
        <div className="px-4 pt-3 max-w-4xl mx-auto">
          <div className="text-[10px] text-yellow-400 mb-1.5 uppercase tracking-wide">
            <i className="fa-solid fa-arrow-right-to-bracket mr-1"></i>
            Issues to include ({pendingInserts.length})
          </div>
          <div className="space-y-1">
            {pendingInserts.map((ann, i) => (
              <div key={i} className="flex items-start gap-2 text-xs bg-yellow-500/5 border border-yellow-500/20 rounded px-2 py-1.5">
                <span className="flex-1 text-gray-300 truncate" title={ann.comment}>
                  <span className="text-yellow-400/70">{ann.issue_type}:</span> {ann.comment}
                </span>
                <button
                  onClick={() => onClearInsert(i)}
                  className="text-gray-500 hover:text-red-400 flex-shrink-0"
                >
                  <i className="fa-solid fa-xmark text-[10px]"></i>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Image previews */}
      {images.length > 0 && (
        <div className="px-4 pt-3 max-w-4xl mx-auto">
          <div className="flex gap-2 flex-wrap">
            {images.map((img, i) => (
              <div key={i} className="relative group">
                <img
                  src={img.dataUrl}
                  alt={img.name}
                  className="w-20 h-20 object-cover rounded border border-gray-700"
                />
                <button
                  onClick={() => removeImage(i)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-600 rounded-full flex items-center justify-center text-white text-[10px] opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <i className="fa-solid fa-xmark"></i>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4">
        <div className="flex gap-3 items-end max-w-4xl mx-auto">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={images.length > 0 ? 'Add a message about the image(s)...' : pendingInserts.length > 0 ? 'Add a message (optional) or send with issues only...' : 'Type a message or paste an image...'}
            disabled={disabled}
            rows={1}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-100 placeholder-gray-500 resize-none focus:outline-none focus:border-blue-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!canSend}
            className="px-4 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg text-sm font-medium transition-colors"
          >
            <i className="fa-solid fa-paper-plane"></i>
          </button>
        </div>
      </form>
    </div>
  )
}
