# Chat model providers (Mistral first)

Goal: configure OpenAI-compatible providers from the web Settings page; every chat
model a provider serves becomes selectable in web chat and in the Android app.

Delivered in three phases, one PR each: backend (store, resolution, model catalog),
web (Settings card + chat picker), Android (picker + model refs).

## Addressing

A provider model is the service string `<provider-id>:<model-id>`
(`mistral:mistral-large-latest`), stored in the existing `main_service` /
`sidekick_service` / `model_service` columns — no schema change, same trick as
`openrouter:<id>`.

- Docker container names cannot contain `:`, so the colon alone separates a provider
  model from a local service.
- `openrouter` is a reserved provider id; that prefix keeps its own module.
- Parsing is syntax-only (`providers.parse_service`), independent of configuration, so
  a conversation whose provider was deleted fails with "provider not configured"
  instead of being looked up as a Docker service.
- The model id may itself contain `:` (`acme:org/model:tag`); only the first colon
  splits.

## Storage

`dashboard/providers.json` (gitignored, written atomically, mode 0600; override with
`LLM_DOCK_PROVIDERS_FILE`). Its own file rather than a key in `chat_settings.json` so
that secrets live in exactly one place with restrictive permissions.

```json
{ "mistral": { "name": "Mistral", "base_url": "https://api.mistral.ai/v1",
               "api_key_env": "MISTRAL_API_KEY", "api_key": "…", "enabled": true } }
```

Key resolution: a stored `api_key` wins; otherwise `os.environ[api_key_env]`, read at
request time. The dashboard runs as the `llm-dock` systemd unit, so a variable exported
in an interactive shell (`~/.bashrc`) is **not** visible to it — the env route works
only through `dashboard/.env` or the unit's environment. Pasting the key in Settings is
the path that needs no restart.

The key is write-only over HTTP: no response carries it, only `key_source`
(`"stored" | "env" | null`). `PUT` with `api_key` absent keeps the stored key, `null`
removes it — so an edit form that never echoes the key cannot erase it.

## API

| Verb | Path | |
|---|---|---|
| GET | `/api/chat/settings/providers` | `{providers: [public entry], presets}` |
| PUT | `/api/chat/settings/providers/<id>` | create/update; 400 on validation |
| DELETE | `/api/chat/settings/providers/<id>` | 404 when absent |
| POST | `/api/chat/settings/providers/<id>/test` | live `/models` call, never served from cache |
| GET | `/api/chat/providers/models[?refresh=1]` | every **enabled** provider with its chat models |

Model rows: `{id, label, aliases, vision, tools, context_length}`. Each provider row
carries `configured`, `stale` and `error`, so one provider's outage costs its own
models, not the picker.

## Model catalog

`GET <base_url>/models` with the provider key, cached per provider for 15 minutes. The
cache entry is keyed by a hash of base URL + key, so editing either invalidates it. A
failed refresh serves the last good list as `stale: true`; a provider that never
answered reports `error`.

Normalisation, measured against Mistral's live list (64 entries, 2026-11-06):

- Drop entries whose `capabilities.completion_chat` is false (embeddings, OCR,
  transcription, TTS) and entries with a non-null `deprecation`. Providers that publish
  no `capabilities` pass through unfiltered.
- Mistral lists every alias as its own entry (`mistral-large-latest` and
  `mistral-large-2512` are one model). Entries are grouped by `aliases` and each group
  collapses to its shortest `-latest` id, else its first id. 38 chat entries become 14.

All served models are offered; there is no curated shortlist (unlike OpenRouter, whose
catalog is ~400 models).

## Request shape

`template_type` for a provider model is `"provider"` (`reasoning_levels.ENGINE_PROVIDER`).
Requests always carry `model`. No reasoning or sampling fields are mapped for this
engine yet — unverified mappings are worse than none, the rule the rest of the repo
follows.

**Mistral rejects unknown fields.** Measured 2026-11-06 against `mistral-small-latest`:

| Payload | Result |
|---|---|
| plain messages | 200 |
| assistant message carrying `reasoning_content` | **422 `extra_forbidden`** |
| top-level `chat_template_kwargs` | **422 `extra_forbidden`** |
| `tool_choice: "none"` with no tools | 200 |
| replayed tool turn with `<uuid>-<n>` tool-call ids | 200 |

The history replay re-sends `reasoning_content` on assistant turns written by local
thinking models, so a conversation switched onto Mistral would fail on its first
request. `llm_proxy.without_reasoning_content` strips it for the provider engine only;
local engines keep receiving it. The engine-specific field maps (`request_fields`) already
send nothing to an unmapped engine, which is what keeps `chat_template_kwargs` away.

## Not done

- Reasoning levels for provider models (Mistral's `magistral-*` aliases reason; no ladder
  is declared until probed).
- Sampling parameters for the provider engine.
- Providers that are not OpenAI-compatible (Anthropic's native API, Gemini's native API).
