import { useState, useRef, useEffect, forwardRef, useImperativeHandle } from 'react'
import { pickFence } from '../../utils/fence'

// Attach allowlist. Non-image entries are inlined into the outgoing message
// as fenced code blocks (see buildMessage). PDFs are intentionally excluded
// — they can't be extracted client-side without a parser; the full artifact
// store in issue #28 will handle binary uploads.
const ALLOWED_EXT = new Set([
  // text / docs
  'txt', 'md', 'markdown', 'json', 'csv', 'tsv', 'log',
  // code
  'js', 'jsx', 'ts', 'tsx', 'py', 'rb', 'go', 'rs', 'java', 'c', 'h',
  'cpp', 'cc', 'hpp', 'cs', 'php', 'swift', 'kt', 'sh', 'bash', 'zsh',
  'sql', 'html', 'css', 'scss', 'yml', 'yaml', 'toml', 'ini', 'xml',
])

// Cap per-file inlined text — guards against accidentally pasting a 50MB
// log into the prompt. The cap is generous (most code/config files are
// well under this) and produces a visible truncation marker when hit.
const MAX_INLINE_BYTES = 512 * 1024

function fileExt(name) {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ''
}

function isImage(file) {
  return file.type.startsWith('image/')
}

function isAllowed(file) {
  if (isImage(file)) return true
  if (
    file.type.startsWith('text/') ||
    file.type === 'application/json' ||
    file.type === 'text/csv'
  ) {
    return true
  }
  return ALLOWED_EXT.has(fileExt(file.name))
}

function langHintFromName(name) {
  const ext = fileExt(name)
  if (!ext) return ''
  if (ext === 'md' || ext === 'markdown') return 'markdown'
  return ext
}

function formatSize(bytes) {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const ChatInput = forwardRef(function ChatInput({ onSend, disabled, pendingInserts = [], onClearInsert, focusKey }, ref) {
  const [value, setValue] = useState('')
  const [images, setImages] = useState([]) // [{dataUrl, name, size}]
  const [attachments, setAttachments] = useState([]) // [{name, size, type, content, truncated}]
  const [dragOver, setDragOver] = useState(false)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)
  const dragDepth = useRef(0)

  // Imperative API for parents that want to inject text from outside the
  // composer (e.g. the text-selection context menu's "Quote in reply" and
  // "Critique this" actions). Prepends the snippet so an existing draft
  // stays where the user left it, and re-focuses the textarea.
  useImperativeHandle(ref, () => ({
    insertText: (snippet) => {
      if (!snippet) return
      setValue(prev => prev ? `${snippet}\n\n${prev}` : snippet)
      textareaRef.current?.focus()
    },
  }), [])

  // Refocus when the input becomes enabled, and whenever the active
  // conversation changes (focusKey) — so opening/creating a conversation
  // lands the cursor in the composer without an extra click.
  useEffect(() => {
    if (!disabled && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [disabled, focusKey])

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current
    if (ta) {
      ta.style.height = 'auto'
      ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
    }
  }, [value])

  function addTextFile(file) {
    // Push a placeholder synchronously so submit knows a read is in
    // flight. Without this, hitting Enter between file-pick and
    // FileReader.onload would silently drop the attachment AND then
    // resurrect a stale chip in the freshly-cleared composer.
    const token = Symbol('attachment')
    setAttachments(prev => [...prev, {
      token,
      name: file.name,
      size: file.size,
      type: file.type || fileExt(file.name),
      content: null,
      truncated: false,
      pending: true,
    }])
    const reader = new FileReader()
    reader.onload = () => {
      const text = String(reader.result ?? '')
      const truncated = text.length > MAX_INLINE_BYTES
      const content = truncated ? text.slice(0, MAX_INLINE_BYTES) : text
      setAttachments(prev => prev.map(a =>
        a.token === token
          ? { ...a, content, truncated, pending: false }
          : a
      ))
    }
    reader.onerror = () => {
      // Drop the placeholder on read failure so it doesn't wedge the
      // composer in a permanent "pending" state.
      setAttachments(prev => prev.filter(a => a.token !== token))
    }
    reader.readAsText(file)
  }

  function addImageFile(file) {
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

  // Shared ingest path for the attach button, drag-and-drop and paste.
  // Images flow through the existing image pipeline; other allowlisted
  // files are shown as attachment chips (affordance only — transport is #28).
  function ingestFiles(fileList) {
    if (disabled) return
    for (const file of fileList) {
      if (!isAllowed(file)) continue
      if (isImage(file)) {
        addImageFile(file)
      } else {
        addTextFile(file)
      }
    }
  }

  function handlePaste(e) {
    if (disabled) return
    // Route pasted files (images and allowlisted non-images, e.g. copied
    // from the OS file manager) through the same ingest path as the
    // attach button and drag-and-drop. Text paste falls through.
    const files = e.clipboardData?.files
    if (files && files.length > 0) {
      e.preventDefault()
      ingestFiles(files)
    }
  }

  function handleFilePick(e) {
    if (e.target.files?.length) ingestFiles(e.target.files)
    e.target.value = '' // allow re-selecting the same file
  }

  // Only intercept file drags. Non-file drags (e.g. selecting text and
  // dragging it into the textarea) must fall through so the browser's
  // native text-drop behavior still works.
  function isFileDrag(e) {
    return !!e.dataTransfer?.types?.includes('Files')
  }

  function handleDragEnter(e) {
    if (disabled || !isFileDrag(e)) return
    e.preventDefault()
    dragDepth.current += 1
    setDragOver(true)
  }

  function handleDragOver(e) {
    if (disabled || !isFileDrag(e)) return
    e.preventDefault()
  }

  function handleDragLeave(e) {
    if (disabled || !isFileDrag(e)) return
    e.preventDefault()
    dragDepth.current -= 1
    if (dragDepth.current <= 0) {
      dragDepth.current = 0
      setDragOver(false)
    }
  }

  function handleDrop(e) {
    if (disabled || !isFileDrag(e)) return
    e.preventDefault()
    dragDepth.current = 0
    setDragOver(false)
    if (e.dataTransfer?.files?.length) ingestFiles(e.dataTransfer.files)
  }

  function removeImage(idx) {
    setImages(prev => prev.filter((_, i) => i !== idx))
  }

  function removeAttachment(idx) {
    setAttachments(prev => prev.filter((_, i) => i !== idx))
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
    const ready = attachments.filter(a => a.content != null)
    if (ready.length > 0) {
      const blocks = ready.map(a => {
        const lang = langHintFromName(a.name)
        const note = a.truncated ? ` (truncated to ${MAX_INLINE_BYTES} bytes)` : ''
        const fence = pickFence(a.content)
        return `**Attached file: \`${a.name}\`**${note}\n\n${fence}${lang}\n${a.content}\n${fence}`
      }).join('\n\n')
      msg = msg ? `${msg}\n\n${blocks}` : blocks
    }
    return msg
  }

  function handleSubmit(e) {
    e.preventDefault()
    const msg = buildMessage()
    const imgDataUrls = images.map(i => i.dataUrl)
    if ((!msg && imgDataUrls.length === 0) || disabled || anyAttachmentPending) return
    onSend(msg, imgDataUrls.length > 0 ? imgDataUrls : undefined)
    setValue('')
    setImages([])
    setAttachments([])
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const anyAttachmentPending = attachments.some(a => a.pending)
  const canSend = !disabled && !anyAttachmentPending && (value.trim() || images.length > 0 || attachments.length > 0 || pendingInserts.length > 0)

  return (
    <div
      className={`border-t border-border ${dragOver ? 'bg-accent/5' : ''}`}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag-and-drop hint */}
      {dragOver && (
        <div className="px-4 pt-3 max-w-6xl mx-auto">
          <div className="rounded border border-dashed border-accent/50 bg-accent/5 px-3 py-2 text-xs font-mono text-accent flex items-center gap-2">
            <i className="fa-solid fa-paperclip"></i>
            Drop files to attach (images, text, json, csv, code)
          </div>
        </div>
      )}

      {/* Pending inserts — refined hairline chips with the critique accent. */}
      {pendingInserts.length > 0 && (
        <div className="px-4 pt-3 max-w-6xl mx-auto">
          <div className="text-[10px] font-mono text-critique mb-1.5 uppercase tracking-wide">
            <i className="fa-solid fa-arrow-right-to-bracket mr-1"></i>
            Issues to include ({pendingInserts.length})
          </div>
          <div className="space-y-1">
            {pendingInserts.map((ann, i) => (
              <div key={i} className="flex items-start gap-2 text-xs bg-elevated border border-hairline border-l-2 border-l-critique rounded px-2 py-1.5">
                <span className="flex-1 text-fg-muted truncate" title={ann.comment}>
                  <span className="font-mono text-critique">{ann.issue_type}:</span> {ann.comment}
                </span>
                <button
                  onClick={() => onClearInsert(i)}
                  className="text-fg-subtle hover:text-error flex-shrink-0"
                  aria-label="Remove issue"
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
        <div className="px-4 pt-3 max-w-6xl mx-auto">
          <div className="flex gap-2 flex-wrap">
            {images.map((img, i) => (
              <div key={i} className="relative group">
                <img
                  src={img.dataUrl}
                  alt={img.name}
                  className="w-20 h-20 object-cover rounded border border-hairline"
                />
                <button
                  onClick={() => removeImage(i)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-error rounded-full flex items-center justify-center text-white text-[10px] opacity-0 group-hover:opacity-100 transition-opacity"
                  aria-label="Remove image"
                >
                  <i className="fa-solid fa-xmark"></i>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Attachment chips — refined hairline, mono filename/size. */}
      {attachments.length > 0 && (
        <div className="px-4 pt-3 max-w-6xl mx-auto">
          <div className="flex gap-2 flex-wrap">
            {attachments.map((att, i) => (
              <div
                key={i}
                className="group flex items-center gap-2 text-xs bg-elevated border border-hairline border-l-2 border-l-accent rounded px-2 py-1.5 max-w-[260px]"
              >
                {att.pending ? (
                  <i className="fa-solid fa-spinner fa-spin text-accent flex-shrink-0" aria-label="Reading file"></i>
                ) : (
                  <i className="fa-solid fa-file-lines text-accent flex-shrink-0"></i>
                )}
                <span className="font-mono text-fg-muted truncate" title={att.name}>{att.name}</span>
                <span className="font-mono text-fg-subtle flex-shrink-0">{formatSize(att.size)}</span>
                <button
                  onClick={() => removeAttachment(i)}
                  className="text-fg-subtle hover:text-error flex-shrink-0"
                  aria-label="Remove attachment"
                >
                  <i className="fa-solid fa-xmark text-[10px]"></i>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4">
        <div className="flex gap-3 items-end max-w-6xl mx-auto">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,text/*,application/json,.md,.csv,.tsv,.log,.js,.jsx,.ts,.tsx,.py,.rb,.go,.rs,.java,.c,.h,.cpp,.cc,.hpp,.cs,.php,.swift,.kt,.sh,.sql,.html,.css,.scss,.yml,.yaml,.toml,.ini,.xml"
            className="hidden"
            onChange={handleFilePick}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            aria-label="Attach files"
            title="Attach files"
            className="px-4 py-3 bg-surface border border-border hover:border-accent text-fg-muted hover:text-accent disabled:opacity-50 rounded-lg text-sm transition-colors"
          >
            <i className="fa-solid fa-paperclip"></i>
          </button>
          <textarea
            ref={textareaRef}
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={images.length > 0 ? 'Add a message about the image(s)...' : pendingInserts.length > 0 ? 'Add a message (optional) or send with issues only...' : 'Type a message, paste or drop files...'}
            disabled={disabled}
            rows={1}
            className="flex-1 bg-surface border border-border rounded-lg px-4 py-3 text-sm text-fg placeholder-fg-subtle resize-none focus:outline-none focus:border-accent disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!canSend}
            className="px-4 py-3 bg-accent-strong hover:bg-accent-hover text-fg-inverse disabled:bg-surface-strong disabled:text-fg-subtle rounded-lg text-sm font-medium transition-colors"
          >
            <i className="fa-solid fa-paper-plane"></i>
          </button>
        </div>
      </form>
    </div>
  )
})

export default ChatInput
