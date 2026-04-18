import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeRaw from 'rehype-raw'
import rehypeKatex from 'rehype-katex'
import { streamChat } from '../../services/sse'
import { createConversation, getConversation } from '../../services/chat'

export default function SpinoffWindow({ id, conversationId: initialConvId, selectedText, serviceName, parentConversationId, position, onClose, onMinimize, onFocus, onConversationCreated, zIndex }) {
  const [convId, setConvId] = useState(initialConvId || null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [pos, setPos] = useState(position)
  const [size, setSize] = useState({ w: 480, h: 420 })
  const [dragging, setDragging] = useState(false)
  const [resizing, setResizing] = useState(false)
  const [title, setTitle] = useState('Spin-off')
  const dragOffset = useRef({ x: 0, y: 0 })
  const resizeStart = useRef({ x: 0, y: 0, w: 0, h: 0 })
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const abortRef = useRef(null)
  const initRef = useRef(false)

  // Initialize: load existing or create new conversation
  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    async function init() {
      if (initialConvId) {
        // Load existing spinoff conversation
        try {
          const data = await getConversation(initialConvId)
          setConvId(data.id)
          setMessages(data.messages || [])
          setTitle(data.title || 'Spin-off')
        } catch { /* ignore */ }
      }
      // New spinoff — conversation created on first message send
    }
    init()
  }, [initialConvId])

  useEffect(() => { inputRef.current?.focus() }, [])
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])
  useEffect(() => {
    return () => { if (abortRef.current) abortRef.current.abort() }
  }, [])

  // Drag handlers
  function handleMouseDown(e) {
    if (e.target.closest('button') || e.target.closest('input')) return
    setDragging(true)
    dragOffset.current = { x: e.clientX - pos.x, y: e.clientY - pos.y }
    onFocus()
    e.preventDefault()
  }

  useEffect(() => {
    if (!dragging) return
    function handleMove(e) {
      setPos({ x: Math.max(0, e.clientX - dragOffset.current.x), y: Math.max(0, e.clientY - dragOffset.current.y) })
    }
    function handleUp() { setDragging(false) }
    window.addEventListener('mousemove', handleMove)
    window.addEventListener('mouseup', handleUp)
    return () => {
      window.removeEventListener('mousemove', handleMove)
      window.removeEventListener('mouseup', handleUp)
    }
  }, [dragging])

  // Resize handlers
  function handleResizeMouseDown(e) {
    setResizing(true)
    resizeStart.current = { x: e.clientX, y: e.clientY, w: size.w, h: size.h }
    e.preventDefault()
    e.stopPropagation()
  }

  useEffect(() => {
    if (!resizing) return
    function handleMove(e) {
      setSize({
        w: Math.max(320, resizeStart.current.w + (e.clientX - resizeStart.current.x)),
        h: Math.max(250, resizeStart.current.h + (e.clientY - resizeStart.current.y)),
      })
    }
    function handleUp() { setResizing(false) }
    window.addEventListener('mousemove', handleMove)
    window.addEventListener('mouseup', handleUp)
    return () => {
      window.removeEventListener('mousemove', handleMove)
      window.removeEventListener('mouseup', handleUp)
    }
  }, [resizing])

  const sendMessage = useCallback(async (content) => {
    if (streaming || !content.trim()) return

    let currentConvId = convId

    // Create conversation on first message
    if (!currentConvId) {
      try {
        const conv = await createConversation({
          main_service: serviceName,
          title: selectedText.length > 50 ? selectedText.slice(0, 50) + '...' : selectedText,
          parent_conversation_id: parentConversationId,
          selected_text: selectedText,
          main_system_prompt: `You are a helpful assistant. The user has selected the following text and wants to discuss it. Be concise.\n\nSelected text:\n"${selectedText}"`,
        })
        currentConvId = conv.id
        setConvId(conv.id)
        onConversationCreated?.(id, conv.id)
      } catch (err) {
        setMessages(prev => [...prev, { role: 'assistant', content: `Error creating conversation: ${err.message}` }])
        return
      }
    }

    const tempMsg = { id: 'temp-' + Date.now(), role: 'user', content }
    setMessages(prev => [...prev, tempMsg])
    setInput('')
    setStreaming(true)
    setStreamingContent('')

    const controller = new AbortController()
    abortRef.current = controller

    let fullContent = ''

    await streamChat(
      `/chat/conversations/${currentConvId}/messages`,
      { content },
      {
        signal: controller.signal,
        onDelta: ({ content: c }) => {
          if (c) { fullContent += c; setStreamingContent(prev => prev + c) }
        },
        onDone: () => {},
        onMessageSaved: () => {
          setStreamingContent('')
          setStreaming(false)
          // Reload messages from DB
          getConversation(currentConvId).then(data => {
            setMessages(data.messages || [])
            if (data.title && data.title !== 'New Conversation') setTitle(data.title)
          }).catch(() => {})
        },
        onError: (msg) => {
          setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${msg}` }])
          setStreaming(false)
          setStreamingContent('')
        },
      }
    )
  }, [convId, streaming, selectedText, serviceName, id, onConversationCreated])

  function handleSubmit(e) {
    e.preventDefault()
    sendMessage(input)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <div
      onClick={onFocus}
      className="fixed shadow-2xl rounded-xl border border-gray-600 flex flex-col overflow-hidden"
      style={{ left: pos.x, top: pos.y, width: size.w, height: size.h, zIndex, backgroundColor: '#111318' }}
    >
      {/* Title bar */}
      <div
        onMouseDown={handleMouseDown}
        className={`px-3 py-2 border-b border-gray-700 flex items-center justify-between flex-shrink-0 select-none ${dragging ? 'cursor-grabbing' : 'cursor-grab'}`}
        style={{ backgroundColor: '#191c22' }}
      >
        <div className="flex items-center gap-2 text-xs font-medium min-w-0">
          <i className="fa-solid fa-code-branch text-purple-400 text-[10px]"></i>
          <span className="truncate text-gray-300" title={title}>{title}</span>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0 ml-2">
          <button onClick={e => { e.stopPropagation(); onMinimize() }} className="w-6 h-6 flex items-center justify-center text-gray-500 hover:text-yellow-400 hover:bg-gray-700 rounded" title="Minimize">
            <i className="fa-solid fa-minus text-[10px]"></i>
          </button>
          <button onClick={e => { e.stopPropagation(); onClose() }} className="w-6 h-6 flex items-center justify-center text-gray-500 hover:text-red-400 hover:bg-gray-700 rounded" title="Close">
            <i className="fa-solid fa-xmark text-[10px]"></i>
          </button>
        </div>
      </div>

      {/* Context */}
      <div className="px-3 py-1.5 border-b border-gray-800/50 bg-gray-800/20 flex-shrink-0">
        <div className="text-[10px] text-gray-500 italic max-h-10 overflow-auto leading-tight">
          "{selectedText.length > 200 ? selectedText.slice(0, 200) + '...' : selectedText}"
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-auto p-2 space-y-2 min-h-0">
        {messages.map((msg, i) => (
          <div key={msg.id || i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-lg px-3 py-2 text-xs ${
              msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-800 border border-gray-700 text-gray-200'
            }`}>
              {msg.role === 'assistant' ? (
                <div className="prose prose-invert prose-xs max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                  <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeKatex]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap">{msg.content}</p>
              )}
            </div>
          </div>
        ))}

        {streaming && streamingContent && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-lg px-3 py-2 text-xs bg-gray-800 border border-gray-700 text-gray-200">
              <div className="prose prose-invert prose-xs max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeRaw, rehypeKatex]}>
                  {streamingContent}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        )}

        {streaming && !streamingContent && (
          <div className="flex justify-start">
            <div className="rounded-lg px-3 py-2 bg-gray-800 border border-gray-700 text-xs text-gray-400">
              <i className="fa-solid fa-spinner fa-spin mr-1"></i>Thinking...
            </div>
          </div>
        )}

        {messages.length === 0 && !streaming && (
          <div className="text-center text-gray-600 py-4 text-[10px]">Ask about the selected text</div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-gray-700 p-2 flex gap-1.5 flex-shrink-0">
        <input
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about this..."
          disabled={streaming}
          className="flex-1 bg-gray-800 border border-gray-700 rounded px-2.5 py-1.5 text-xs text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 disabled:opacity-50"
        />
        <button type="submit" disabled={streaming || !input.trim()} className="px-2.5 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 rounded text-xs transition-colors">
          <i className="fa-solid fa-paper-plane"></i>
        </button>
      </form>

      {/* Resize handle (bottom-right corner) */}
      <div
        onMouseDown={handleResizeMouseDown}
        className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize"
        style={{ background: 'linear-gradient(135deg, transparent 50%, #4b5563 50%)' }}
      />
    </div>
  )
}
