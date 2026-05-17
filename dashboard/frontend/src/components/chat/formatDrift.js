// Mirrors FORMAT_DRIFT_PATTERNS in dashboard/chat/llm_proxy.py — same kinds,
// same priorities. Detection runs server-side at stream end (persisted via
// parse_warning_json) and client-side on saved messages so old conversations
// without the column populated still surface the chip.

const PATTERNS = [
  {
    kind: 'arg_key_tags',
    regex: /<arg_key>/,
    description: 'Model emitted `<arg_key>` XML tags in content — Qwen3.6 family format drift.',
  },
  {
    kind: 'arg_value_tags',
    regex: /<arg_value>/,
    description: 'Model emitted `<arg_value>` XML tags in content — Qwen3.6 family format drift.',
  },
  {
    kind: 'function_text_tag',
    regex: /<function=/,
    description: 'Model emitted `<function=…>` text instead of a structured tool_call.',
  },
  {
    kind: 'json_codeblock_call',
    regex: /```(?:json|tool_code)\s*\{[\s\S]{0,40}"(?:name|tool|function)"\s*:/,
    description: 'Model emitted a JSON tool call in a markdown codeblock instead of structured tool_calls.',
  },
  {
    kind: 'orphan_tool_call_tag',
    regex: /<tool_call>/,
    description: 'Model emitted a `<tool_call>` tag in content — parser likely failed to consume it.',
  },
  {
    kind: 'orphan_close_function',
    regex: /<\/function>/,
    description: 'Model emitted a stray `</function>` close tag — partial/malformed tool call.',
  },
]

export function detectFormatDrift(message) {
  if (!message) return null
  const content = message.content || ''
  for (const p of PATTERNS) {
    const m = p.regex.exec(content)
    if (m) {
      const start = Math.max(0, m.index - 40)
      const end = Math.min(content.length, m.index + m[0].length + 160)
      let snippet = content.slice(start, end)
      if (start > 0) snippet = '…' + snippet
      if (end < content.length) snippet = snippet + '…'
      return { kind: p.kind, snippet, description: p.description }
    }
  }
  // Silent-drop heuristic: parser ate everything, leaving reasoning but no
  // visible content and no tool_calls. Most confusing failure mode in the UI.
  const trimmed = content.trim()
  const reasoning = (message.reasoning_content || '').trim()
  const toolCalls = message.tool_calls || []
  if (!trimmed && reasoning && toolCalls.length === 0) {
    return {
      kind: 'silent_drop',
      snippet: '',
      description: 'Model emitted reasoning but no content and no tool calls. Parser may have silently dropped a malformed tool call.',
    }
  }
  return null
}

export const DRIFT_KIND_LABEL = {
  arg_key_tags: '<arg_key> drift',
  arg_value_tags: '<arg_value> drift',
  function_text_tag: '<function=…> drift',
  json_codeblock_call: 'JSON-in-codeblock drift',
  orphan_tool_call_tag: 'orphan <tool_call>',
  orphan_close_function: 'orphan </function>',
  silent_drop: 'silent drop (parser ate response)',
}
