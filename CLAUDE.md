# LLM-Dock — Claude operational notes

Tactical playbook for adding / running models in this llm-dock instance.
The general developer guide is in `AGENTS.md`; this file holds gotchas
that don't fit there.

## Adding a new vLLM service from the CLI

Workflow when the dashboard isn't open or you want a scripted change:

1. **Download the model into the HF cache.** Containers run with
   `HF_HUB_OFFLINE=1` (set in `dashboard/templates/vllm.j2`), so anything
   the model needs must already be on disk before the container starts.
   ```
   /home/teodor/.local/bin/hf download <org>/<model>
   ```
2. **Append a service entry to `services.json`.** Keys: `alias`, `port`,
   `api_key`, `model_name`, `params` (dict of CLI flags), `template_type:
   "vllm"`. Pick a free port in 3300–3399 (used ports are visible in
   `services.json` itself).
3. **Rebuild `docker-compose.yml` from `services.json`.** Don't edit the
   generated section directly — it's between `BEGIN DYNAMIC` /
   `END DYNAMIC` markers and gets clobbered. Instead:
   ```
   cd /github/teo-mateo/llm-dock/dashboard && venv/bin/python -c "
   from compose_manager import ComposeManager
   mgr = ComposeManager('/github/teo-mateo/llm-dock/docker-compose.yml',
                        '/github/teo-mateo/llm-dock/services.json')
   mgr.rebuild_compose_file()"
   ```
4. **Bring the container up.** `cd /github/teo-mateo/llm-dock && docker
   compose up -d <service-name>`. Use `--force-recreate` after editing
   params on an existing service.
5. **Tail logs to verify.** `docker logs -f <service-name>` — wait for
   `Application startup complete` or `Uvicorn running on http://0.0.0.0:8000`.

## Gotchas

### vLLM ≥0.20 removed `--task`

In vLLM 0.20.x (the version in `llm-dock-vllm`), the old `--task embed`
flag is gone. Use:

- `--runner pooling` — instead of `--task embed` (also `auto`, `draft`,
  `generate`)
- `--convert embed` — picks the embed pooler when the model could be used
  for multiple pooling tasks (also `auto`, `classify`, `none`)

To explore the current arg surface inside the image:

```
docker run --rm --gpus all --entrypoint vllm llm-dock-vllm serve --help=all 2>&1 | grep -- '--<flag>'
```

(Without `--gpus all`, `vllm serve --help` aborts in pydantic device
validation before printing the parser.)

### Custom-arch models need both their repos cached

Models with `trust_remote_code` often reference Python modules in a
*different* HF repo via `auto_map`. Example: `nomic-ai/nomic-embed-text-v1.5`'s
config.json points to `nomic-ai/nomic-bert-2048--modeling_hf_nomic_bert`,
so you must download **both**:

```
hf download nomic-ai/nomic-embed-text-v1.5
hf download nomic-ai/nomic-bert-2048
```

Symptom if you forget: container exits with
`OSError: We couldn't connect to 'https://huggingface.co' to load the
files, and couldn't find them in the cached files.`

### Embedding services should keep `--gpu-memory-utilization` low

The big chat models commonly take 0.55–0.94. An embedding service running
alongside them only needs a sliver — set it to ~0.10 or less so it
doesn't try to grab KV cache that's already reserved.

### Unknown flag names are silently dropped

`render_cli_flag()` in `flag_metadata.py` is permissive: any string
starting with `-` passes through to the rendered command unchanged.
That's why arbitrary vLLM flags work in `params` without metadata
entries — but it also means a **typo** in the flag name (e.g. `--gpu-mem`)
ships to the container as-is and fails at startup, not at config time.
Verify with `mgr.preview_service(name)` before bringing the container up.

## Default API key rotation

All model services share one **default API key**: `LLM_DOCK_API_KEY` in
`dashboard/.env` (exposed as `config.GLOBAL_API_KEY`), mirrored into every
service's `api_key` in `services.json`. The dashboard can rotate it in one
click (Services table → "Rotate default key"):

- `GET /api/default-api-key/rotation-preview` — impact only, mutates
  nothing: counts services, lists running containers (will be stopped) and
  Open WebUI-registered services (keys go stale).
- `POST /api/default-api-key/rotate` — generates a new key, writes it to
  `.env` via `config.set_global_api_key()`, rewrites every `services.json`
  entry, rebuilds `docker-compose.yml`, then **stops** every running
  affected container (they keep the revoked key in memory; they are not
  auto-restarted — start them manually afterwards).

Gotchas:

- Reference `config.GLOBAL_API_KEY` (the module attribute), not a
  `from config import GLOBAL_API_KEY` name binding — only the attribute
  reflects an in-process rotation without a dashboard restart.
- **Open WebUI is not touched.** It stores its own copy of each
  connection's key in its sqlite DB; after rotation those are stale and
  must be re-entered manually under Open WebUI → Admin → Settings →
  Connections. The preview/rotate responses list the affected services.
- Core rotation logic is `key_rotation.rotate_keys_in_db()` (pure, unit
  tested in `dashboard/tests/test_key_rotation.py`); container stops and
  preview live in `routes/services.py`.

## Adding an external MCP server

Built-in MCP tools live in `dashboard/chat/mcp_registry.py` and ship with
the repo. External MCP servers (machine-local — their venv, path, and
config live outside this repo) are declared in a JSON file on disk,
default `dashboard/mcp_servers.json` (gitignored). Override via
`LLM_DOCK_MCP_SERVERS_FILE`.

Shape — one entry per server id, top-level object keyed by id. See
`dashboard/mcp_servers.example.json` for a working example.

```json
{
  "my-tool": {
    "enabled": true,
    "name": "My Tool",
    "description": "What the user sees in the chat toggle",
    "command": "/abs/path/to/venv/bin/python",
    "args": ["/abs/path/to/server.py", "--transport", "stdio"],
    "icon": "fa-magnifying-glass",
    "tool_hint": "System-prompt suffix telling the model when to use this tool."
  }
}
```

Rules enforced at load time:

- `command` must be an **absolute path**. No `shell=True`, no PATH lookup.
- `id` must not contain `__` (collides with `server_id__tool_name`
  namespacing in `mcp_client.py`).
- `id` must not collide with a built-in (`sympy-math`, `schemdraw-circuits`,
  `render-html`). Built-ins always win.
- All of `name`, `description`, `command`, `args`, `icon`, `tool_hint` are
  required; `enabled` defaults to `true`.

Editing the file:

- **From the UI**: `/tools` page in the dashboard. Edit the JSON, hit Save
  (server-side validation, atomic write, auto-reload), or fix on disk and
  hit Reload from disk.
- **From the CLI**: edit the file with your editor, then `curl -X POST
  -H "Authorization: Bearer $TOKEN"
  http://localhost:3399/api/chat/mcp-registry/reload`.

Secrets stay in the external MCP server's own `.env`; the registry only
holds paths.

## Editing the default chat system prompt

Every new conversation inherits a global default `main_system_prompt`. It
is **editable from the dashboard** — Tools page → "Default system prompt"
card — so iterating on it no longer needs a code edit + service restart.

- **Storage:** `dashboard/chat_settings.json` — a JSON singleton,
  gitignored (machine-local, holds user prompt text). If it's absent,
  unreadable, malformed, or has no `main_system_prompt` key, the built-in
  `DEFAULT_MAIN_SYSTEM_PROMPT` in `dashboard/chat/constants.py` is used.
  Override the path with `LLM_DOCK_CHAT_SETTINGS_FILE`.
- **API** (bearer auth), `/api/chat/settings/main-system-prompt`:
  - `GET` → `{current, builtin, customized}` — `customized` is true only
    when a non-empty override is stored *and* it differs from the
    built-in, so it's safe to drive a "modified" indicator off it.
  - `PUT {"content": "..."}` → store the override (rejects empty /
    whitespace-only content, and non-object JSON bodies, with 400).
  - `DELETE` → drop the override, reverting to the built-in.
- `create_conversation` reads the configured default **only** when the
  request body has no explicit `main_system_prompt`. Existing
  conversations are unaffected — each carries its own copy in `chat.db`.
- Core logic is `chat/settings_store.py` (pure, unit-tested in
  `dashboard/tests/test_settings_store.py`); endpoints + the
  conversation-creation integration test live in
  `dashboard/tests/test_chat_settings_routes.py`.

**Keep tool-specific guidance out of this prompt.** Anything about how to
use a particular tool (web search, sympy, schemdraw, render-html, …)
belongs in that MCP server's `tool_hint` — it is appended to the system
prompt by `mcp_registry.get_tool_hints()` only when the server is enabled
for the conversation. The base prompt should hold only generic style /
accuracy / tool-posture guidance. See
`dashboard/mcp_servers.example.json` for the `websearch` `tool_hint`
carrying the web-research guidance.

## Reference: working embedding service

`vllm-nomic-embed-text-v1.5` (port 3320) — see `services.json`. Smoke
test:

```
curl -s -X POST http://localhost:3320/v1/embeddings \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"model":"vllm-nomic-embed-text-v1.5","input":"search_document: hello"}'
```

Returns 768-dim float vectors. Use `search_document:` prefix on stored
text and `search_query:` prefix on queries (Nomic's matryoshka task
prefixes).
