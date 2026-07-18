# Feature spec (draft) — Conversation Artifacts

> Status: discussion. Becomes its **own** GitHub issue (separate from the
> visual-redesign "what we keep" issue).

## Intent (from user)

A conversation-scoped store of files/images that:

1. The **user can upload** to a conversation.
2. The **model can generate**.
3. Are **persisted** (user leans: in the DB as binary; files won't be large).
4. Are shown in a **tree-like structure under the conversation**.
5. Belong to the **main/root conversation only — not spin-offs**.
6. The **user can delete**.
7. The **user can reference in chat** (attach/mention into a message).
8. Are managed by the model via **internal tools**: list / fetch / create
   (at minimum).

User acknowledges this is a larger change.

## Hard constraint: naming collision

Existing `Artifact` (DB table `artifacts`): `id, message_id,
artifact_type, content TEXT, title, language` — per-message,
model-generated **text** render outputs (code / HTML / SVG via
`ArtifactRenderer.jsx`, render-html MCP). The new concept is
conversation-scoped binary files. Must resolve naming/relationship
(Decision A).

## Environment facts

- DB is **SQLite** (`chat.db`, with a `_migrate()` path) — BLOBs are fine;
  keep blob bytes in a **separate table** so conversation/message row scans
  don't drag large payloads.
- Built-in model tools live under `chat/mcp_registry.py` (built-in MCP
  servers like sympy-math, render-html). New artifact tools = a new
  built-in tool group.
- Images already supported as multimodal message content; text/binary
  files are new.

## Decisions (RESOLVED)

- **A. Naming/collision → UNIFY.** One conversation-scoped artifact store.
  The existing per-message render outputs become a subtype of artifact
  (`source = 'render'`). Single term across the app: **Artifacts**
  (not nautical — consistent with D1).
- **B. Storage → DB blob, separate table.** Metadata table +
  `conversation_artifact_blobs` for bytes. **10 MB/file** cap, MIME
  allowlist (images, text, pdf, json, csv, common code) — configurable
  constant.
- **C. Tree → left sidebar, nested under the conversation**, grouped by
  origin: **Uploaded** / **Generated** (Generated includes both model
  `create_artifact` outputs and migrated render outputs).
- **D. Spin-offs → read-only access.** A spin-off can list / get /
  reference the **root** conversation's artifacts; it cannot create,
  delete, or own any. Storage and the tree stay on the root conversation.

## Resulting data model (FINAL)

`projects`
: `id`, `name`, `created_at`, `archived_at` NULLable,
  `default_main_service`, `default_sidekick_service`,
  `default_system_prompt`, `default_mcp_servers` (project-level defaults
  new conversations inherit; all NULLable).

`conversations`
: + `project_id` **NULLable** FK. Spin-offs inherit their parent's
  `project_id` (enforced equal: a spin-off is in the same project — or
  same loose state — as its parent).

`artifacts`
: `id`, `owner_project_id` NULLable, `owner_conversation_id` NULLable
  (**exactly one set** — CHECK/invariant), `name`, `mime_type`,
  `size_bytes`, `sha256`, `source` ∈ {`upload`,`model`,`render`},
  `origin_message_id` NULLable (set for `model`/`render`), `title`,
  `language` (carried for render outputs), `created_at`,
  `deleted_at` NULLable.

`artifact_blobs`
: `artifact_id` (PK/FK), `bytes` BLOB. One row per artifact; kept off the
  hot conversation/message rows.

### Scope resolver (the one rule that replaces root-only/read-only)

```
resolve_artifact_owner(conversation):
    c = walk_to_root(conversation)          # spin-off -> its root
    if c.project_id is not None:  return ("project", c.project_id)
    else:                         return ("conversation", c.id)
```

- In-project conversations (root + spin-offs) **share** the project's
  artifacts. Loose conversations + their spin-offs share the **root
  conversation's** artifacts. Create writes to the resolved owner;
  list/get/reference read the resolved owner. No special spin-off rule —
  spin-offs simply resolve to their lineage's scope (read+reference;
  create allowed since it lands on the shared owner).

## Migration (UNIFY + Project — one-way, in `_migrate()`)

1. **Projects**: create one auto-named project per existing **root**
   conversation that you want grouped — DEFAULT: leave existing
   conversations **loose** (`project_id = NULL`) to preserve today's
   behavior; projects are opt-in going forward. (Alt., if you'd rather
   auto-wrap each root conv in a 1-conv project, say so — affects only the
   migration step.)
2. **Render outputs → artifacts**: for each existing `artifacts` row
   (`message_id, artifact_type, content, title, language`): resolve the
   message's conversation owner via the resolver above; insert an
   `artifacts` row with `source='render'`,
   `origin_message_id = message_id`, mime from artifact_type/language,
   name synthesized; write `content` (utf-8) into `artifact_blobs`.
   `ArtifactRenderer` keeps rendering inline by `origin_message_id`. Old
   table kept read-only during transition, then dropped. **Back-compat
   preserved.**

## Proposed defaults (apply unless overridden)

- **Deletion**: soft delete (`deleted_at`). A message that referenced a
  now-deleted artifact (incl. a render output) shows a "deleted"
  placeholder; history preserved. **User-only — the model has no delete
  tool.**
- **Model tools** (new built-in group `conversation-artifacts`):
  `list_artifacts()`, `get_artifact(id)`, `create_artifact(name, mime,
  content_b64)`. Scoped server-side to the active conversation's root
  (model cannot pass an arbitrary conversation id); spin-off callers get
  read-only (list/get) against the root, `create` denied.
- **Referencing UX**: composer picker (paperclip → "from this
  conversation"). Images inlined as multimodal blocks; small text inlined;
  large/binary exposed by id for `get_artifact` to fetch on demand
  (bounded context).
- **Generation/render flow**: model `create_artifact` → metadata + blob
  written → appears in the tree (Generated) and as a chip in the producing
  message. Render outputs additionally keep their existing inline render.

## Out of scope (for now, note in issue)

Versioning / update-in-place, cross-conversation sharing, artifact diff,
external object storage. Capture as "future" so the first cut stays small.
