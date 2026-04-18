# Chat Feature Requirements

## Overview
A chat page integrated into the LLM-Dock dashboard that allows conversing with running models. A secondary "sidekick" model provides critique capabilities and is also available as a tool the main model can consult autonomously.

## Phases

### Phase 1 (MVP)
- Chat interface with model selection, conversation persistence, critique feature
- No MCP / tool support

### Phase 2
- MCP tool support (web search, file access, etc.)
- Sidekick-as-MCP-server (main model can consult sidekick autonomously)
- MCP server configuration UI

## Core Concepts

### Two-Model Architecture
- **Main model** — the primary conversational model the user interacts with
- **Sidekick model** — a secondary model (ideally from a different vendor/training lineage) that serves as a **critic** when the user requests a critique of the main model's response
- Each model has its own **configurable system prompt**, allowing distinct personalities (e.g. helpful assistant vs skeptical reviewer)
- Models are expected to be similar in capability but independently trained, reducing shared hallucination patterns
- Default pairing: **Gemma 4 31B** (Google) as main, **Qwen 3.5 27B** (Alibaba) as sidekick

### Model Selection
- Automatically discover running llama.cpp services and present them as selectable models
- Select a **main model** and optionally a **sidekick model** from running services
- Update available models dynamically as services start/stop

## Features

### Chat Interface
- Standard chat UI with user/assistant message bubbles
- Markdown rendering in responses
- **Inline HTML rendering** — if the model responds with HTML, render it inline (similar to Open WebUI behavior)
- Streaming responses (SSE from llama.cpp's OpenAI-compatible API)
- **Thinking/reasoning display** — both models output `reasoning_content` (chain-of-thought); display in a collapsible block above the response

### Conversation Persistence (SQLite)
- Conversations stored in SQLite database
- Conversation list sidebar (like ChatGPT / Claude AI)
- Create new conversations, switch between existing ones
- **Edit past messages** — editing a user message removes all subsequent messages (user + assistant) and re-submits from that point
- Delete conversations

### Critic Feature (User-Initiated)
- A button on each assistant response to request a critique from the sidekick model
- The critique is a direct API call to the sidekick — no MCP needed
- **Context window**: send the last N messages (user + assistant content only, **no reasoning/thinking content**) to give the critic conversational context
- Critic returns **structured output** (JSON) identifying specific spans of the original response with annotations
- Highlighted spans in the original response with tooltip/popover bubbles explaining each issue
- Visual distinction between the original response and critique annotations

### System Prompts
- Separate configurable system prompts for main model and sidekick model
- Defaults that reflect their roles (assistant vs reviewer)
- Editable per-conversation or globally

## Technical Notes
- Both models served via llama.cpp's OpenAI-compatible API
- API keys are stored per-service in `services.json` — the chat backend can read them directly
- Both models support 262K context window (Q8 quantization)
- Gemma 4 on port 3316, Qwen 3.5 on port 3304 (dynamic, discovered from running services)

## Open Questions
- Model parameter controls (temperature, top_p, etc.)?
- Export conversations?
- Select text + right-click "critique this" for partial critique?
- How to visually represent sidekick consultations in the chat UI? (Phase 2)
