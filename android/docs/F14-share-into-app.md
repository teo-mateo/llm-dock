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
      force-stop (bytes copied to app storage at intent time — the
      source `content://` grant does not outlive the receiving
      activity).
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

The `EXTRA_STREAM` content must be **copied into app storage
immediately** on intent receipt — the read grant is valid only for the
receiving activity's lifetime.

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
- F14-R6's "New conversation" row navigates to the existing `NEW_CHAT`
  destination; on `onConversationCreated` the staged content is
  reassigned to the new conversation id.

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
- **No mockup exists for this feature.** The 16 validated screens have
  no share-target screen; the picker is specified from the conversation
  list's visual language rather than a signed-off drawing.
- **PDFs and binary files are rejected**, even though the system share
  sheet offers them to most apps. The web UI excludes PDFs for the same
  reason (no client-side parser); declaring `application/pdf` in the
  intent filter and then failing at parse time would be worse than not
  appearing for them at all.

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
  consume-once, clear-on-leave), `ShareTargetViewModel` (four states,
  ordering), thread apply-once semantics.
- **Device:** extend `android/scripts/dev.sh` with share helpers, e.g.
  `dev.sh share-text "…"` and `dev.sh share-image <uri>`, wrapping
  `adb shell am start -a android.intent.action.SEND …`. Image shares
  need a real `content://` URI — push a file and reference it via the
  app's own FileProvider or MediaStore, since bare `file://` URIs are
  restricted on modern Android.
- **Process-death criteria (F14-R5)** are the reason `dev.sh clear` /
  force-stop are part of the verification loop: stage → force-stop →
  relaunch → content still staged.
