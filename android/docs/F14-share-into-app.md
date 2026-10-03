# F14 · Share into llm-dock

**Mockup:** none — this is a new feature with no mockup screen (see *Deviations*) ·
**Depends on:** F01 (auth gating), F02 (list data), F04 (composer + send) ·
**Blocks:** nothing

Share content from anywhere on the phone into a conversation: the app
appears in the system share sheet, the user picks which chat the content
goes to, and it lands **staged in the composer** — attached or typed in,
but not sent. The user edits and sends normally.

---

## 1. Research findings

What the codebase already has, and the constraints that shape this
feature.

### The Android app today

- **`MainActivity`** has only a `MAIN`/`LAUNCHER` intent filter and the
  default `standard` launch mode. `exported=true` already.
- **The composer** (`ThreadViewModel`) holds `composer: String` +
  `attachments: List<String>` (data URLs). `send()` posts
  `{content, images}` to `POST /api/chat/conversations/<id>/messages`
  and streams the reply. **Nothing about the send path needs to change.**
- **Image attachments (F04-R9)** already exist: gallery via
  `PickVisualMedia`, camera via `TakePicture` + FileProvider, both
  downscaled to ≤1568 px edge, JPEG q85, base64 data URL
  (`ImageAttachments.kt`). Attachments render in bubbles via
  `decodeDataUrl` (`ThreadMessages.kt:99`).
- **Draft text** is persisted per conversation in DataStore
  (`DraftStore`), surviving process death and the 401 round trip
  (F00-R3). **Attachments are not persisted** — a known gap recorded in
  F04: they live only in `ThreadViewModel._state`, and the fix is
  described as "files in `cacheDir` keyed by conversation, with the draft
  record pointing at them".
- **The conversation list** (`ConversationsRepository.list()`) calls
  `GET /api/chat/conversations?limit=-1&unfiled=true` — one consistent
  snapshot, `updated_at DESC` (**most recent first, exactly what the
  share picker needs**), project threads hidden (decision 3).
- **Navigation** (`Destinations`): `CONNECT`, `TABS` (CHATS/MODELS),
  `THREAD` (`thread/{conversationId}`), `NEW_CHAT`. Thread ViewModels are
  keyed per conversation. `AppRoot` decides the start destination from
  stored server/token/credential; `SessionState.authenticationRequired`
  is observed at the NavHost root and routes to Connect.
- **Auth** (F01-R6): a stored credential silently re-authenticates on
  401, so a signed-in user never sees Connect unless re-auth fails.

### The backend (`dashboard/chat/`)

- `POST /api/chat/conversations/<id>/messages` accepts `{content, images}`
  where `images` is a list of **data URLs**. `llm_proxy.build_messages_array`
  sends every entry to the model as `{"type":"image_url","image_url":{"url":…}}`.
  There is **no file-attachment concept anywhere** — any non-image data
  URL in `images` would be sent to the model as an image and fail.
- Ground rule **R-A (backend parity)** — no new server code — therefore
  holds: file attachments as a first-class concept are off the table.

### The web UI (parity reference, R-B)

`ChatInput.jsx` is the behaviour bar the phone must match:

- **Images** → data URL into `images` (same encoding as the phone).
- **Text/code files** (allowlist: `txt, md, markdown, json, csv, tsv,
  log, js, jsx, ts, tsx, py, rb, go, rs, java, c, h, cpp, cc, hpp, cs,
  php, swift, kt, sh, bash, zsh, sql, html, css, scss, yml, yaml, toml,
  ini, xml`, plus anything with `text/*` or `application/json` MIME) are
  **read as text and inlined into the message content** as a fenced code
  block — `**Attached file: \`name\`**` then a ```lang fence — capped at
  `MAX_INLINE_BYTES = 512 * 1024` with a visible truncation note. The
  comment in the source calls this "affordance only — transport is #28".
- **PDFs are deliberately excluded** — "can't be extracted client-side
  without a parser".

So the honest answer to "a file should be attached like a picture" is:
**the backend cannot attach files, and the web doesn't either — it
inlines text files into the message.** The phone must do the same.

---

## 2. The feature

From the system share sheet, llm-dock offers a target picker — a list of
the user's conversations, most recent first. Picking one opens that
thread with the shared content staged in the composer:

| Shared content | Lands as |
|---|---|
| text / link (`text/plain` + `EXTRA_TEXT`) | composer text, editable |
| image (`image/*` + `EXTRA_STREAM`) | an image attachment (removable), same pipeline as F04-R9 |
| text/code file (`text/*`, `application/json`, allowlisted code ext) | inlined fenced code block in the composer (web parity) |
| anything else (PDF, binary) | a clear error, nothing staged |

**Nothing is sent.** The composer is pre-filled; the user edits, removes,
or sends as usual. The staged content must survive process death between
the pick and the send.

---

## 3. Requirements

### F14-R1 · Share target registration (Must)

The app appears in the system share sheet for text, links, images and
text-type files, and a share routes to the **existing** app instance
rather than stacking a second one.

**Acceptance criteria**

- \[x\] `adb shell am start -a android.intent.action.SEND -t text/plain
      --es android.intent.extra.TEXT "hello"` opens the app on the
      target picker.
- \[x\] Sharing an image \(`-t image/png --eu android.intent.extra.STREAM
      <content-uri>`) opens the picker with the image staged.
- \[x\] A share arriving while the app is already open (on any screen)
      brings the app forward and shows the picker — no second activity
      instance, one back press from the picker returns to where the app
      was.
- \[x\] The share sheet does not list the app for `application/pdf` or
      `application/octet-stream` unless the intent filter genuinely
      accepts them (see *Deviations* — binary MIME types are not
      declared).

### F14-R2 · Target picker (Must)

A full-screen list of conversations, most recent first, from which the
user chooses where the content goes.

**Acceptance criteria**

- \[x\] Rows are ordered `updated_at DESC` (the same data and ordering as
      the Chats tab).
- \[x\] Each row shows the title, the model, and a relative time — the
      same row visual as the conversation list.
- \[x\] Project threads are absent (fetched with `unfiled=true`, decision
      3).
- \[x\] Loading, empty and failed states per F00-R5; the empty state says
      what would fill it.
- \[x\] Picking a row opens that thread with the content staged (F14-R3).
- \[x\] Back or a dismiss action clears the pending share and returns to
      the Chats tab — nothing is left staged anywhere.
- \[x\] A consumed share does not come back on recreation — rotation,
      Recents re-activation, or process-death restore keep the current
      destination and do not re-stage the delivery; a genuinely new send
      still replaces the pending record (issue 261).

### F14-R3 · Staging by content type (Must)

The shared content lands in the composer, editable and removable, and is
**never sent automatically**.

**Acceptance criteria**

- \[x\] Text/link: the composer is pre-filled with the shared text; the
      user can edit it before sending.
- \[x\] Image: an attachment thumbnail appears in the composer strip and
      is individually removable; the image is downscaled through the
      existing F04-R9 pipeline (≤1568 px, JPEG).
- \[x\] Text/code file: the composer is pre-filled with
      `**Attached file: \`name\`**` plus a fenced code block of the file
      content, truncated at 512 KB with a visible note — matching the
      web UI's inline format.
- \[x\] A message with only the staged content (no extra text) is sendable
      — `canSend` treats staged content like typed content.
- \[x\] Unsupported content \(PDF, binary\): the picker shows the server
      error pattern — a readable message, nothing staged, the list still
      usable.
- \[x\] No request is issued to the dashboard until the user presses Send.

### F14-R4 · Auth gating (Must)

A share that arrives while signed out lands on Connect, and the share
flow resumes after sign-in.

**Acceptance criteria**

- \[x\] Cold start from a share with no stored session: Connect appears;
      after successful sign-in the target picker appears (not the Chats
      tab).
- \[x\] A share arriving while the app is on Connect is not lost: after
      sign-in the picker shows the staged content.
- \[x\] Dismissing the picker after sign-in returns to the Chats tab with
      nothing staged.

### F14-R5 · Staged content survives process death (Must)

Between the share and the send, the staged content must survive the
app being killed — the user's "adapt before sending" window is exactly
where Android reclaims the app.

**Acceptance criteria**

- \[x\] Share text → pick a chat → force-stop the app → relaunch: the
      thread opens with the text still in the composer.
- \[x\] Same for an image: the attachment is still staged after a
      force-stop (bytes copied to app storage as soon as the provider
      read finishes — the source `content://` grant does not outlive
      the receiving activity).
- \[x\] A 401 round trip \(F00-R3\) does not lose the staged content.
- \[x\] Sending or leaving the thread clears the staged record — the next
      visit to the thread shows no ghost attachment.

### F14-R6 · New conversation from the share (Should)

The picker offers a "New conversation" entry at the top, which runs the
existing F03 flow; the staged content then lands in the newly created
thread.

**Acceptance criteria**

- \[x\] Choosing it opens the new-chat sheet; after the conversation is
      created, the thread opens with the content staged.
- \[x\] Backing out of the new-chat sheet returns to the picker with the
      content still staged.

### F14-R7 · Summarize a shared page (Must) — issue 255

A `text/plain` share carrying an HTTP(S) link offers one primary action,
**Summarise**, that creates a thread on the remembered model, enables a
page-fetching tool on it, and sends one prepared turn that instructs the model
to read the page before summarising it. Availability is decided by
`GET /api/chat/mcp-servers?probe=url-fetch`, whose verdict is each tool's
parameter schema — never an entry name, because a `websearch`-only install
sounds retrieval-capable and cannot open the shared URL.

**Acceptance criteria**

- \[x\] A share of a bare link, and of a link inside prose, both surface the
      action (`SharedUrlExtractorTest`).
- \[x\] An image or text-file share never surfaces it (`SharedKindParserTest`,
      `ShareTargetViewModelTest`).
- \[x\] Ordinary sharing is unchanged: picking a row still stages the content
      unsent (`ThreadShareTest`, `ShareTargetViewModelTest` green untouched).
- \[x\] No turn is submitted unless the probe found a server that can fetch a
      URL, and no claim is filed if the tools write fails
      (`SummarizeCoordinatorTest`).
- \[x\] Configuration failure, tool-not-answering, and an old dashboard each
      read differently on the picker, with a next step
      (`ShareTargetViewModelTest`).
- \[x\] A remembered model that is missing or stopped opens the model choice
      with the share still staged (`SummarizeCoordinatorTest`).
- \[x\] A send that never reached the server restores the prepared turn to the
      composer (`ThreadAutoSendTest`).
- \[x\] Force-stop, reopen, and re-visit never submit the turn twice; the claim
      is owed once (`SharedDraftStoreAutoSendTest`, `ThreadAutoSendTest`).
- \[ \] Device: share a real article, tap Summarise, watch the fetch tool card
      appear before the summary — `dev.sh share-text "<url>"`.
- \[ \] Device: with the fetcher disabled in the dashboard, the action is absent
      and the reason names what to enable.
- \[ \] Device: tap, force-stop before the first token, relaunch — exactly one
      user turn in the thread.

---

## 4. Design

### 4.1 Intent handling

- Add `ACTION_SEND` intent filters to `MainActivity`:
  - `text/plain` (links and text)
  - `image/*` (photos)
  - `text/*`, `application/json` (text files)
  - a small set of code MIME types matching the web allowlist
    (`application/x-python`, `text/x-java`, `application/javascript`,
    `text/x-sh`, …) — or rely on `text/*` + `application/json` plus a
    filename-extension fallback for the rest, matching `isAllowed()`'s
    `ALLOWED_EXT` set.
- Switch the activity to `android:launchMode="singleTask"` and handle
  `onNewIntent`: the share intent is delivered to the existing instance,
  the task comes forward, and the back stack is preserved (one back from
  the picker returns to where the app was). `singleTask` is the standard
  share-target pattern; `standard` would stack a second activity.
- `MainActivity` stays dumb: it parses the intent into a
  `PendingShare` and hands it to a container-level store; the NavHost
  reacts.

### 4.2 Content parsing (`SharedContentParser`)

Pure, unit-testable. Input: `Intent` (action, type, `EXTRA_TEXT`,
`EXTRA_STREAM`, `EXTRA_TITLE`). Output: a sealed `SharedContent`:

- `SharedText(text)` — from `EXTRA_TEXT`; also `EXTRA_TITLE`/`EXTRA_SUBJECT`
  folded in when the text is a bare link (decision 4.7).
- `SharedImage(uri)` — `image/*`; decoded lazily through the existing
  `readImage`/`toDataUrl` pipeline.
- `SharedTextFile(name, content, truncated)` — read as UTF-8, capped at
  512 KB, formatted as the web's fenced block when staged.
- `Unsupported(reason)` — PDF/binary/unknown; surfaces the error.

Precedence rules (decision 4.7): `EXTRA_TEXT` wins for `text/plain`;
`EXTRA_STREAM` wins for `image/*`; a `text/plain` share with only
`EXTRA_STREAM` is a text file.

The `EXTRA_STREAM` content must be **read while the receiving activity is
alive** — the read grant is valid only for that lifetime — and written to app
storage before the picker hands the share to a conversation. The read is not
allowed on the main thread: the picker opens on a "reading" placeholder, the
consuming actions unlock when the bytes land, and an import cut short by
process death leaves no placeholder behind (the user re-shares rather than the
picker sitting on "reading" forever).

### 4.3 Pending-share store

A container-level store (`AppContainer`), because the share must survive
navigation, the Connect round trip, and process death:

- **In memory:** the unassigned `PendingShare` (text + attachment
  records), consumed once when the user picks a target.
- **On disk:** the staged record persisted as JSON in DataStore
  (small: text + attachment file names + metadata), attachment bytes as
  files in `cacheDir/shared-drafts/`. This is the "files in cacheDir
  keyed by conversation" shape the F04 known gap already prescribes —
  scoped to shared content, not retrofitted onto the general composer.

Flow:

1. Intent → parse → stage to disk → store in memory.
2. Picker → user picks conversation → **reassign**: text written into
   `DraftStore.save(conversationId, text)` (existing mechanism — the
   thread's `loadedFrom` already merges the draft), attachment files
   moved under the conversation's key, disk record cleared.
3. Thread opens → `ThreadViewModel` reads the per-conversation
   attachment record on `load()` → applies to `attachments` → clears.
   Consume-once semantics make the repeated `load()` on re-entry a no-op.

### 4.4 Picker screen

- New destination `Destinations.SHARE_PICKER` (`share_picker`), pushed
  on top of `TABS` without the bottom bar, like `THREAD`/`NEW_CHAT`.
- A `ShareTargetViewModel` over `ConversationsRepository.list()` — the
  same four states as `ConversationListViewModel` (F00-R5), no
  selection/swipe/delete semantics. Rows reuse the `ConversationRow`
  visual (`ConversationListScreen.kt:415`).
- Header shows what is being shared (a thumbnail for images, a file
  name, or the first line of text) so the user sees the payload before
  choosing.
- Back clears the pending share (F14-R2).
- F14-R6's "New conversation" row is the first row of the list, above
  the conversations; it navigates to the existing `NEW_CHAT` destination,
  and on `onConversationCreated` the staged content is reassigned to the
  new conversation id.

### 4.5 Thread integration

- `ThreadViewModel`'s factory (in `AppNavHost`) gains the attachment
  draft store; on `load()` it applies any per-conversation staged
  attachments to `attachments` and clears the record.
- No change to `send()`, `PendingUserMessage`, or the wire format —
  staged content is just composer state.
- The composer's existing attachment strip and removable thumbnails
  already render the staged image; the inline text file is just composer
  text.

### 4.6 Auth gating

- `AppRoot`/NavHost observes the pending-share store. When a share is
  pending and the user is signed in, navigate to `SHARE_PICKER` instead
  of the default destination (cold start) or in addition to the current
  screen (warm).
- `onSignedIn` (Connect) checks the store before navigating to `TABS`.
- Because the store is in the container, it survives the Connect
  round trip untouched.

### 4.7 Decisions

| Decision | Choice | Why |
|---|---|---|
| `ACTION_SEND_MULTIPLE` | Out of scope for v1 | The ask is one item. Note in *Out of scope*; reopening is cheap (same parser, list of streams). |
| `EXTRA_TEXT` vs `EXTRA_STREAM` precedence | `EXTRA_TEXT` wins for `text/plain`; `EXTRA_STREAM` wins for `image/*` | Apps like WhatsApp send a link as text *and* a preview image; the user asked for the link in the composer. |
| `EXTRA_TITLE`/`EXTRA_SUBJECT` | Folded into a bare-link share only | Prevents a bare URL from being sent with no context. |
| New conversation row | Should (F14-R6) | Natural share target; reuses F03 unchanged. |
| Persistence scope | Shared content only | Fixing the general F04 attachment gap is a separate change; the cacheDir shape built here is the same one that fix needs, so this is the natural pilot. |
| Binary/PDF files | Rejected with a message | Web parity — the web excludes PDFs; there is no client-side extraction. |

---

## 5. Endpoints used

| Method | Path | Use |
|---|---|---|
| GET | `/api/chat/conversations?limit=-1&unfiled=true` | Picker list (existing `ConversationsRepository.list()`) |
| POST | `/api/chat/conversations` | F14-R6 — new conversation (existing F03 path) |
| POST | `/api/chat/conversations/<id>/messages` | Send — unchanged, only after the user presses Send |
| GET | `/api/chat/mcp-servers?probe=url-fetch` | F14-R7 — which enabled servers can fetch a URL |

No new endpoints, no new server code (R-A).

---

## 6. Deviations

- **"A file is attached like a picture" does not match the backend.**
  The `images` field is the only attachment mechanism and every entry is
  sent to the model as `image_url`; there is no file-attachment endpoint
  and R-A forbids adding one. The web UI's answer is to inline text
  files into the message, and this feature does the same (F14-R3).
  Recorded here so the plan never describes a file attachment the
  backend cannot hold.
- **Provider reads moved off the main thread** (issue 278). The intent
  originally decoded, downscaled, compressed and wrote the shared bytes inside
  `onCreate`, and a gallery pick or camera capture did the same inside its
  result callback — hundreds of milliseconds of UI freeze on a camera-sized
  original, and an unbounded stall on a cloud-backed provider stream. Intake now
  claims the delivery's identity synchronously and reads the bytes on the
  application's I/O scope, which is why a stream-backed share appears in the
  picker as a placeholder first: the alternative is a picker that opens late
  enough to look broken. Two consequences the UI carries rather than hides: the
  consuming actions wait for the content, and a slow provider is visible as
  "Reading shared content…".
- **No mockup exists for this feature.** The 16 validated screens have
  no share-target screen; the picker is specified from the conversation
  list's visual language rather than a signed-off drawing.
- **PDFs and binary files are rejected**, even though the system share
  sheet offers them to most apps. The web UI excludes PDFs for the same
  reason (no client-side parser); declaring `application/pdf` in the
  intent filter and then failing at parse time would be worse than not
  appearing for them at all.
- **F14-R6 shipped in the wrong branch of the picker.** The entry was
  wired into the empty state only, so a phone with at least one
  conversation — every real phone — saw no way to start a chat to share
  into, and the criterion still read as met because the test fixture had
  no conversations. It is now the first row of the loaded list, which is
  what "at the top" asked for. The empty-state button stays: it is the
  same navigation, and that state has no list to put a row in.
- **F14-R7 breaks rule R-A, deliberately.** `?probe=url-fetch` is one
  additive query parameter on an endpoint the app already calls; without
  it the phone cannot tell whether a configured server can fetch a URL at
  all — `GET /api/chat/mcp-servers` carries no tool names, and the route
  that does is the dashboard-only `mcp-registry/test`. A name heuristic
  would have kept R-A and lost R3: it selects `websearch`, which answers
  from prior knowledge while looking like a summary. Issue 255 permits
  backend changes where they are the cleanest implementation, and F15 set
  the precedent for a phone feature shipping its own backend (PR #128).
- **F14-R7's "the conversation must say so" is read as two surfaces.** A
  turn that was never started has no conversation to say anything in, so
  a setup failure (no tool, dashboard too old, tool not answering) is a
  reason on the picker where the action would have been, and only a
  failure after a legitimate send — the fetch itself failing, or returning
  nothing useful — is reported inside the thread. Creating a thread to hold
  an error message would be a worse answer than refusing to create one.
- **Summarize always creates a new thread.** Enabling a tool means writing
  `mcp_servers_json` on the conversation, and `send_message` reads the tools
  from the stored row, so an existing thread would have its model and tool
  set rewritten by a tap that looked like "summarise this". The ordinary
  picker rows still stage the share into whatever thread the user picks.
- **"Nothing is left staged anywhere" is enforced at intake, not by wiping
  the store (issue 261).** The picker's consume-once rule used to hold only
  because `MainActivity` re-staged the launch intent on every `onCreate` —
  which is also how a consumed share came back on rotation. It is now held
  by a per-delivery claim: the activity stamps each served `ACTION_SEND`
  intent with a content identity (`ShareDeliveryToken`) and records it
  durably in `handled.json`, and `ShareIntakeGate` refuses any redelivery of
  an already-served intent — via the mark, or via the claim when the process
  died in the background and the mark rides only in the task record. The
  pending record itself is still never cleared on restore, because that is
  F14-R5's hydration contract; the claim deliberately outlives
  `clearPending`/`reassign`/`clear` so the next reader does not "simplify"
  this back into a `savedInstanceState == null` check (which rotation
  defeats, `savedInstanceState` being non-null there) or a restore that
  wipes the store (which would break R5 and the Connect round trip, and
  would still replay on plain rotation). One accepted cost: the
  pending-share observer now also skips while the new-chat sheet is open, so
  a share arriving under the sheet updates the record the sheet will consume
  but does not navigate; the picker regains it on the sheet's exit.

---

## 7. Out of scope

- `ACTION_SEND_MULTIPLE` (multiple photos/files in one share).
- General composer attachment persistence (the F04 known gap) — the
  cacheDir mechanism built here is the seed of that fix, but applying it
  to the ordinary attach button is a separate change.
- Sharing into a project thread (the phone has no project concept —
  decision 3; the picker uses `unfiled=true` like the Chats tab).
- Receiving shares while the dashboard is unreachable — the picker
  shows its normal failed state (F00-R4).

---

## 8. Verification notes

- **JVM tests:** `SharedContentParser` (MIME classification, text-file
  truncation, precedence rules), the pending-share store (reassign,
  consume-once, clear-on-leave, write ordering on the I/O scope),
  `ShareTargetViewModel` (four states,
  ordering), thread apply-once semantics, `ShareImport` (what needs a read at
  all, the typed failure when the provider throws, a late read losing to a newer
  share), `ThreadAttachmentImportTest` (the composer's busy/arrived/failed
  states for a pick).
- **Device:** extend `android/scripts/dev.sh` with share helpers, e.g.
  `dev.sh share-text "…"` and `dev.sh share-image <uri>`, wrapping
  `adb shell am start -a android.intent.action.SEND …`. Image shares
  need a real `content://` URI — push a file and reference it via the
  app's own FileProvider or MediaStore, since bare `file://` URIs are
  restricted on modern Android.
- **Process-death criteria (F14-R5)** are the reason `dev.sh clear` /
  force-stop are part of the verification loop: stage → force-stop →
  relaunch → content still staged.
