import { useState, useCallback, useRef, useEffect } from 'react'
import { getConversation } from '../services/chat'
import { streamChat } from '../services/sse'

export default function useChat() {
  const [conversation, setConversation] = useState(null)
  const [messages, setMessages] = useState([])
  const [critiques, setCritiques] = useState({})
  const [streaming, setStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingReasoning, setStreamingReasoning] = useState('')
  const [toolEvents, setToolEvents] = useState([])
  const [artifacts, setArtifacts] = useState({}) // {messageId: [artifact]}
  const [streamingArtifacts, setStreamingArtifacts] = useState([])
  const [error, setError] = useState(null)
  const abortRef = useRef(null)

  const loadConversation = useCallback(async (convId) => {
    // Abort any in-flight stream before switching
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setStreaming(false)
    setStreamingContent('')
    setStreamingReasoning('')
    setToolEvents([])
    setStreamingArtifacts([])
    setError(null)

    try {
      const data = await getConversation(convId)
      setConversation(data)
      setMessages(data.messages || [])
      setCritiques(data.critiques || {})
      setArtifacts(data.artifacts || {})
    } catch (err) {
      setError(err.message)
    }
  }, [])

  const sendMessage = useCallback(async (content, images) => {
    if (!conversation || streaming) return
    setError(null)
    setStreaming(true)
    setStreamingContent('')
    setStreamingReasoning('')
    setToolEvents([])
    setStreamingArtifacts([])

    // Optimistically add user message
    const tempUserMsg = {
      id: 'temp-user',
      role: 'user',
      content,
      images: images || [],
      seq: messages.length > 0 ? messages[messages.length - 1].seq + 1 : 1,
    }
    setMessages(prev => [...prev, tempUserMsg])

    const controller = new AbortController()
    abortRef.current = controller

    let fullContent = ''
    let fullReasoning = ''

    const body = { content }
    if (images && images.length > 0) body.images = images

    await streamChat(
      `/chat/conversations/${conversation.id}/messages`,
      body,
      {
        signal: controller.signal,
        onDelta: ({ content: c, reasoning_content: r }) => {
          if (c) {
            fullContent += c
            setStreamingContent(prev => prev + c)
          }
          if (r) {
            fullReasoning += r
            setStreamingReasoning(prev => prev + r)
          }
        },
        onToolCall: (evt) => {
          // Save any reasoning that happened before this tool call
          const reasoning = fullReasoning || undefined
          setToolEvents(prev => [...prev, { type: 'call', ...evt, reasoning }])
          // Reset reasoning for next segment
          setStreamingReasoning('')
          fullReasoning = ''
        },
        onToolResult: (evt) => {
          setToolEvents(prev => [...prev, { type: 'result', ...evt }])
          // Reset streaming content — model will start a new response
          setStreamingContent('')
          fullContent = ''
        },
        onArtifact: (evt) => {
          setStreamingArtifacts(prev => [...prev, evt])
        },
        onDone: () => {
          // Will be followed by message_saved
        },
        onMessageSaved: (data) => {
          const assistantMsg = {
            id: data.message_id,
            role: 'assistant',
            content: fullContent,
            reasoning_content: fullReasoning || null,
            model_service: conversation.main_service,
            seq: data.seq,
          }
          setMessages(prev => {
            // Replace temp user msg with real one, add assistant
            const updated = prev.filter(m => m.id !== 'temp-user')
            // Re-add user with proper seq
            const userMsg = { ...tempUserMsg, id: 'user-' + (data.seq - 1), seq: data.seq - 1 }
            return [...updated, userMsg, assistantMsg]
          })
          setStreamingContent('')
          setStreamingReasoning('')
          setStreaming(false)
          // Reload to get proper IDs from server
          loadConversation(conversation.id)
        },
        onError: (msg) => {
          setError(msg)
          setStreaming(false)
          setStreamingContent('')
          setStreamingReasoning('')
          // Remove temp message on error
          setMessages(prev => prev.filter(m => m.id !== 'temp-user'))
        },
      }
    )
  }, [conversation, messages, streaming, loadConversation])

  const editMessage = useCallback(async (msgId, content) => {
    if (!conversation || streaming) return
    const msg = messages.find(m => m.id === msgId)
    if (!msg || msg.role !== 'user') return

    setError(null)
    setStreaming(true)
    setStreamingContent('')
    setStreamingReasoning('')

    // Truncate messages from this point
    setMessages(prev => {
      const truncated = prev.filter(m => m.seq < msg.seq)
      return [...truncated, { ...msg, content, id: 'temp-edit' }]
    })

    const controller = new AbortController()
    abortRef.current = controller

    let fullContent = ''
    let fullReasoning = ''

    await streamChat(
      `/chat/conversations/${conversation.id}/messages/${msgId}`,
      { content },
      {
        method: 'PUT',
        signal: controller.signal,
        onDelta: ({ content: c, reasoning_content: r }) => {
          if (c) {
            fullContent += c
            setStreamingContent(prev => prev + c)
          }
          if (r) {
            fullReasoning += r
            setStreamingReasoning(prev => prev + r)
          }
        },
        onDone: () => {},
        onMessageSaved: () => {
          setStreamingContent('')
          setStreamingReasoning('')
          setStreaming(false)
          loadConversation(conversation.id)
        },
        onError: (msg) => {
          setError(msg)
          setStreaming(false)
          setStreamingContent('')
          setStreamingReasoning('')
          loadConversation(conversation.id)
        },
      }
    )
  }, [conversation, messages, streaming, loadConversation])

  const stopStreaming = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
      setStreaming(false)
    }
  }, [])

  // Abort streaming on unmount (e.g. navigating away)
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort()
        abortRef.current = null
      }
    }
  }, [])

  return {
    conversation,
    messages,
    critiques,
    setCritiques,
    streaming,
    streamingContent,
    streamingReasoning,
    toolEvents,
    artifacts,
    streamingArtifacts,
    error,
    loadConversation,
    sendMessage,
    editMessage,
    stopStreaming,
    setConversation,
  }
}
