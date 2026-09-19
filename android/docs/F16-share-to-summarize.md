# F16 · Share a URL into a one-tap summarize thread

**Mockup:** none — post-mockup feature, and the web client has no share target to copy (see *Deviations*) ·
**Depends on:** F14 (share intake, staging, picker), F03 (new-chat sheet, tools PUT), F04 (composer, send), F07 (MCP tools), F02 (service state) ·
**Blocks:** nothing

A link shared from any app on the phone can become a summarised answer in one tap:
the share picker grows a single row above its conversation list, and tapping it
creates a thread on the remembered model, gives that thread the fetch/search tools,
and sends the instruction — the thread opens already generating.

This is the one place in the app where content arriving from another app is sent
without the user pressing Send. F14's rule that a share is *staged, never sent* is
kept everywhere it was written; the row is a separate action the user takes
explicitly, not a share that happens to send itself.

---

## 1. Research findings

### The issue's premise, checked against the code

Issue #252 claimed the new-chat sheet could start a conversation with MCP tools
already enabled, and that the work was wiring plus a setting. Both halves are true,
and the second is smaller than it sounds:

- `NewChatViewModel` already takes `preselectedMcpServerIds`, intersects it with the
  registry, and issues the create-then-`PUT /mcp-servers` pair (F03-R1's fifth
  criterion, F03-R4's preselect rule). Nothing there needed changing beyond letting
  the caller pass a list.
- `ChatRepository.send(...)` needs nothing beyond `SendMessageRequestDto(content)` —
  `images`, `reasoningLevel`, `sourceMessageDbId` are all omitted when null, so a
  plain-text first turn is an ordinary turn. The tools are conversation state, so
  they apply to that first message.
- **There was no settings screen to add a row to.** F13 is planned and unbuilt, and
  F14's settings gear was a disabled placeholder. The issue's "one more row in
  Settings" therefore presupposed a surface that does not exist; see *Deviations*.

### The one hard requirement: no double send

A thread that opens and immediately sends has exactly one window where a crash or a
relaunch leaves the app unable to tell "already sent" from "never sent" — the gap
between writing the auto-send intent and the server accepting the message. The server
has no field for "send this next", so whatever marks it must be local and must be
gone before the request goes out. That is the shape of everything below.

---

## 2. The feature

From the system share sheet, when the payload is text containing an `http(s)://`
URL, the picker offers:

> **[sparkle] Summarize this page** — *Creates a new thread and asks for a summary*

One tap on it runs, in order:

1. `GET /api/services` — the remembered model must still exist, be running, and be
   chat-capable (not `open-webui`, not an embedder).
2. `POST /api/chat/conversations` with that `main_service`, no system prompt.
3. `PUT /api/chat/conversations/<id>/mcp-servers` with the configured tool ids.
4. The per-conversation staged-message record is written with the prompt + URL,
   **the auto-send marker is written to disk**, and the app navigates to the thread.
5. `ThreadViewModel.load()` hydrates the composer from the staged record,
   **consumes the marker**, and calls the ordinary `send()`.

When step 1 finds no usable model the sheet appears instead, with the tools already
selected. When step 3 fails the thread still opens, the message is staged, nothing
sends, and the screen says why.

The prompt sent is `Summarize prompt` + a blank line + the URL alone — not the whole
shared text, which is often the page title plus commentary (F14 decision 4.7). The
rest of the share text stays available by using an ordinary picker row instead.

---

## 3. Requirements

### F16-R1 · The row appears only where it means something (Must)

One row, above the conversation list and outside it, shown when the pending share is
text (not an image, not an inlined text file), contains an `http(s)://` URL, and at
least one configured summarize tool is in `GET /api/chat/mcp-servers`. Its subtitle
says what the tap does — the row is the promise, the settings rows hold the details —
and it appears only when it can be kept.

**Acceptance criteria**

- [x] A `text/plain` share containing a URL shows the row, reading "Summarize this
      page / Creates a new thread and asks for a summary".
- [x] A text share with no URL shows no row, and every F14 row behaves exactly as
      before.
- [x] An image share shows no row even when its caption contains a URL.
- [x] An inlined text file that quotes a URL shows no row — the classification, not
      the string, decides.
- [x] With no summarize tool available, the row is gone: the app never offers to
      fetch with a tool it does not have.

### F16-R2 · One tap creates, arms and sends (Must)

The row is one action, not a wizard: no confirmation, no intermediate screen. Three
requests, then the thread — open, with the user's message rendered and the reply
streaming (F04-R2's "user's message first" holds because this is the ordinary send
path, not a second one).

**Acceptance criteria**

- [x] From the share sheet to a generating thread in one tap on the row.
- [x] The thread carries the configured tools (`GET /api/chat/conversations/<id>`
      reports them) before the message is sent — the PUT precedes the POST.
- [x] Exactly one user turn exists in the new thread, and its content is the
      configured prompt, a blank line, and the URL.
- [x] The pending share is cleared, so returning to the picker does not offer a
      second summarize.
- [x] The new thread appears in the Chats list, and the model is now the
      remembered one (F03's rule, unchanged).

### F16-R3 · The auto-send is consumed exactly once (Must)

The marker is a file under the staged-share directory, written before navigation and
deleted by the read that acts on it. It is never part of any request body, so there is
no code path by which a reconnect, a reattach (F09) or a re-entry could replay it.

**Acceptance criteria**

- [x] Relaunching the app on a thread that already auto-sent does not send again.
- [x] Force-stop between the tap and the send: the message is still staged and the
      marker is still armed, so the thread completes the flow on the next visit —
      once.
- [x] A failed send leaves nothing to re-send on its own; the text is back in the
      composer (F04's 409 rule).

### F16-R4 · No usable model falls through to the sheet (Must)

No remembered model, one that has been deleted, one that stopped running, or one that
is not chat-capable → the new-chat sheet with the summarize tools already selected.
No conversation is created by the row itself, and the flow stays armed: creating the
thread continues it.

**Acceptance criteria**

- [x] A remembered model that is stopped opens the sheet, and creates nothing.
- [x] The sheet arrives with those tools selected, not the remembered selection
      (F03-R4's preselect rule, one source of truth for this flow).
- [x] A tool id the registry no longer reports is dropped rather than offered.
- [x] Creating the thread from there continues the flow under F16-R2's rules,
      including the auto-send.

### F16-R5 · A failed tools write sends nothing (Must)

If the `PUT` fails the conversation would answer with no way to read the page, which
is the one failure mode a summarize has to refuse rather than degrade into: an answer
invented from the URL. The message is staged, the reason is shown above the composer,
and the user sends by hand if that is what they want.

**Acceptance criteria**

- [x] With the `PUT` failing, the thread opens, nothing is sent, and the notice
      says the tools could not be enabled and that sending is the user's choice.
- [x] The message is in the composer and `canSend` is true — the notice is not a
      dead end.
- [x] A failed `POST` create leaves the picker where it was, with the server's
      words and the share still staged (F14's picker rules).
- [x] The notice is gone on the next visit to that thread.
      *(The one device row this could not carry: producing a failing `PUT` needs a
      fault injected server-side — see Verification notes.)*

### F16-R6 · Prompt and tools are settings, filtered against the registry (Must)

Two rows, wherever settings live today: the prompt (with **Reset** back to the
built-in) and the tool chips. Stored ids are filtered against
`GET /api/chat/mcp-servers` on every read, so a renamed tool stops being offered
rather than being silently dropped at send time. The first read preselects
`webfetch` + `websearch` so the feature works untouched.

**Acceptance criteria**

- [x] Editing the prompt changes what the next summarize sends.
- [x] **Reset** returns to the built-in wording and the row reports it as default.
- [x] Unchecking every tool removes the summarize row for URL shares — the honest
      consequence, not a disabled control — and the tool rows themselves stay on
      screen with the reason above them, so the choice is reversible.
- [x] A stored id missing from the registry is neither offered nor sent.

---

## 4. Design

### 4.1 Classification carries an origin

`StagedShare` gains `origin: StagedOrigin` (`TEXT` / `IMAGE` / `TEXT_FILE` /
`UNSUPPORTED`), set where `MainActivity` classifies the intent. The URL test
(`SharedKindParser.containsUrl`) is a helper on the parser, so the pattern lives in
one place. The row's visibility and the URL extraction share one function
(`SummarizePlanner.urlIn`), which is why the two can never disagree.

### 4.2 One pure decision function

`SummarizePlanner.plan(share, prompt, toolIds, availableToolIds, rememberedModel, services)`
returns `Hidden`, `CreateOn(model, message, toolIds)` or `PickModelFirst(message, toolIds)`.
It takes the service snapshot as an argument, so the freshness policy lives at the call
site (the row must read live state, not the snapshot the picker loaded for its list —
F15's lesson about a value materialised for one service).

### 4.3 The auto-send marker

`SharedDraftStore` owns it: `armAutoSend(conversationId)` writes
`<cacheDir>/shared-drafts/<conversationId>/autosend`, `takeAutoSend(...)` deletes it
and reports whether it was there. Per-conversation files are read with a numbered-file
filter so `autosend` and `notice.txt` are never mistaken for attachments. Reusing the
staged-share directory keeps F14's lifecycle in one place: `clearConversation` and
`clearPending` already cover it, which is the force-stop guarantee.

`ThreadViewModel.load()` reads the staged notice and takes the marker *before* the
state reaches `Loaded`, so no frame is ever emitted with the composer empty; it then
calls the ordinary `send()`. There is no second send path in the app.

### 4.4 The fall-through

`AppNavHost` passes `container.sharedDraftStore.peekSummarize()?.toolIds` into the
sheet, and its `onConversationCreated(id, toolsApplied)` calls
`consumeSummarize(id, drafts, store, toolsApplied)` — the same three steps the picker
takes, run from the sheet's callback. `consumeSummarize` is the only place that arms
the marker, so the two entry points cannot drift.

### 4.5 Settings

`feature/settings/` holds the two rows, reachable from the gear in the Chats header
(`chats_settings_button`), which is where mockup 02 draws a settings gear. F13 will
replace the screen; the rows and `SummarizePreferences` are meant to be lifted into it
unchanged.

---

## 5. Endpoints used

| Method | Path | Use |
|---|---|---|
| GET | `/api/chat/mcp-servers` | Row visibility, tool chips, fall-through filtering |
| GET | `/api/services` | The live gate in F16-R2 step 1, and the model named on the row |
| POST | `/api/chat/conversations` | The new thread (existing F03 path) |
| PUT | `/api/chat/conversations/<id>/mcp-servers` | The tools, before any message exists |
| POST | `/api/chat/conversations/<id>/messages` | The first turn — the ordinary send path |

No new endpoints, no new server code (R-A).

---

## 6. Deviations

- **F14-R3's "nothing is sent automatically" does not hold for this row.** Issue #252
  asks for a one-tap action; a row that stages a summarize the user then sends by hand
  is a two-tap feature wearing a one-tap label. The rule survives on every ordinary
  picker row, and this row is a distinct, labelled control rather than a share that
  sends itself — F14-R3's actual subject is a staged payload with no second thought.
- **No mockup exists**, and none was authored: this is a single row in a screen F14
  already specifies from the conversation list's visual language, plus two rows in a
  settings surface F13 will design properly. Drawing a 17th screen for one list row
  would create a drawing to maintain without settling anything.
- **R-B (web parity) does not apply.** There is nothing to port from: the web client
  has no share target, and the issue's web references (the new-chat sheet's
  `preselectMcpServerIds` flow, `ChatInput.jsx`'s tool menu) are about the machinery
  this reuses. Recorded because this is the first Android feature with no web sibling.
- **Settings live on a new route rather than in F13's sheet**, because F13 does not
  exist. The issue's "add a row to what exists" was checked against the code, not the
  plan: F14's gear was drawn as a no-op placeholder, and wiring it to a real route is
  the smallest honest reading of "a setting" — the alternative was a hardcoded prompt
  behind a gear that still did nothing.
- **Tools are a create-then-`PUT` pair, not part of the `POST`.** The server takes no
  tool field on create (and R-A forbids adding one), so one tap costs three requests
  and opens a second failure mode. That is exactly why F16-R5 is a requirement: with
  the tools as a separate write, the half-created thread is a real state the user can
  land in, not a hypothetical.
- **The auto-send marker is local state, and consumed before the request.** There is no
  server-side place for "send this next", and a marker deleted at read is the only
  shape that cannot replay. The residual race (killed between the delete and the
  server's accept) loses the summarize rather than duplicating it — the direction a
  network client should fail in.
- **The URL alone is sent, not the shared text.** `EXTRA_TEXT` from another app is
  frequently a title plus commentary; the issue asks for the page summarised. F14's
  ordinary rows keep the verbatim text, so nothing is lost — only the summarize row
  extracts.
- **The row's copy states the action, not the settings.** The first draft read
  "New thread, fetch and search on, sent as soon as you tap" — three settings named
  in the order a config file lists them, two of which the user may well have changed.
  It now states what the tap does. The tool ids belong to F16-R6's settings row, and
  the guarantee the copy needs to keep is carried by the row's visibility instead.
- **The row sits above the list, outside it, and disappears when it does not apply** —
  unlike F14-R6's "New conversation", which is permanently part of the list. A
  conditional row inside the list shifts the position of everything under it, and a
  row that does not apply is not an option to grey out.
- **No model or tool choice on the path**, by design. The remembered model and the
  configured tools are what make it one tap; the sheet (F16-R4) is where choice
  happens, and the settings rows are where the tools are chosen durably.
- **The fall-through arms through `peekSummarize()`, not navigation arguments.** Tool
  ids in a route argument would be a second copy of the same state, and the sheet is
  already reached from three places. The pending intent is the single source, and the
  navigation destination carries no payload.

---

## 7. Out of scope

- F13 proper (the real Settings sheet, text size, default tools), which absorbs these
  two rows later.
- Share targets beyond `ACTION_SEND` (`ACTION_SEND_MULTIPLE` stays F14's exclusion),
  and sharing into a project thread (the phone has no project concept — F14 decision 3).
- A `SUMMARIZE` action or a pinned app shortcut that skips the picker.
- Choosing tools or a model per share from the row itself — both live in settings and
  the new-chat sheet.
- Following up automatically (a second turn asking for key quotes), which is the user
  pressing Send again.
- A prompt template language (`{url}`, `{domain}`). The prompt is prose and the URL is
  appended; a substitution language for one variable is more surface than the feature.

---

## 8. Verification notes

- **JVM:** `SummarizePlannerTest` (visibility incl. image/text-file exclusion, tool
  filtering, routing on remembered/missing/stopped/embedder, trailing punctuation),
  `SharedDraftStoreTest` (marker consumed once, notice lifecycle, `clearPending`
  clearing the armed flow, numbered-attachment filtering against the sibling files),
  `ShareTargetViewModelTest` (row states, three-call order and PUT body, failed create
  leaves the share staged, failed PUT stages + notices + withholds, no-model fall-through
  creates nothing), `ThreadShareTest` (auto-send sends on load, second visit silent,
  withheld notice sends nothing), `NewChatViewModelTest` (preselect beats remembered,
  unknown id dropped).
- **Device:** `./scripts/dev.sh share-text "…"`, `ui`, `shot`, `force-stop`, `token`;
  dashboard reads over HTTP with the token from `dev.sh token`.

| Criterion | How verified |
|---|---|
| R1 row appears for a URL | device — a `text/plain` share of a real article URL, `am start … -n com.hpz.llmdockchat/.MainActivity`; the row read "Summarize this page / Creates a new thread and asks for a summary" (`f16-03-picker-row`) |
| R1 no URL, no row | device — the same share with prose and no link: the picker went straight from the payload card to the list |
| R1 image, no row | device for the rejected-image case (`f16-15-image-share`); the staged-image case is unit — pushing a `content://` image the picker would accept proved flakier than the rule it tests |
| R1 text file quoting a URL | unit (`SummarizePlannerTest`, `ShareTargetViewModelTest`) — origin, not the string, decides |
| R1 no tool, no row | device — all tools unchecked in Settings, same URL share: no row; one tool re-checked: row returned (`f16-09-tools-off`, `f16-11-tools-recoverable`) |
| R2 one tap to a generating thread | device (`f16-04-thread-generating`) — user message rendered, reasoning block open, `webfetch · fetch_readable` and `webfetch · fetch_txt` tool rows already live while the answer streamed |
| R2 tools before the message | device + API — `GET /api/chat/conversations/<id>` reported `["webfetch","websearch"]`, and the turn's own tool calls are the proof they were live on message one |
| R2 one turn, exact content | API — the new conversation held exactly one message, `user`, whose content was the configured prompt, `\n\n`, and the bare URL (the shared text's "Kimi K3 is here:" commentary was dropped, as designed) |
| R2 pending share cleared | device + `run-as` — `cache/shared-drafts` held no pending record after the tap |
| R3 no double send | device — force-stop mid-generation, relaunch: the conversation still held exactly one `user` and one `assistant` message; unit for the marker itself (consume-once, `clearPending`) |
| R3 killed before create | device — force-stop ~0.7 s after the tap: no conversation was created, and `run-as find` showed no `autosend` marker and no staged-share directory left behind |
| R4 stopped remembered model | device — the remembered model in `llm_dock.preferences_pb` was rewritten (via `run-as`) to `llamacpp-gemma-4-26b-a4b-it-q8`, which is stopped; the tap opened the sheet, which said "The model used last time isn't running — pick one to continue" with **Web Fetch** preselected (`f16-12-fallthrough-sheet`) — no container was started or stopped |
| R4 create continues the flow | device + API — creating from that sheet produced a thread with `["webfetch"]` and exactly one auto-sent user message (`f16-14-fallthrough-sent`) |
| R5 withheld send | unit only — a MockWebServer 500 on the `PUT`, asserting the thread opens, the message is staged, `canSend` is true, no send fires, and the notice is what the screen shows. Device row outstanding: it needs a fault injected server-side, and the only client-reachable failure of that call is the network — which fails the create first, a different branch |
| R5 failed create | unit (`ShareTargetViewModelTest`) |
| R6 prompt edit round-trips | device — the field was cleared and retyped, the state read `Custom` (`f16-07-settings-saved`), and the *next* summarize's first message carried the new wording verbatim, read back over the API |
| R6 reset | device — **Reset** restored the built-in text and the state read `Built-in default` again |
| R6 tools drive the row | device, both directions |
| R6 unknown id dropped | unit (`NewChatViewModelTest`) — a stored id the registry does not report is neither selected nor offered |
| F14 unchanged | device — an ordinary picker row still stages the share in the composer with nothing sent (`f16-05-staged-not-sent`), and the thread's message count was unchanged afterwards |

What the device pass caught, that unit tests could not have:

1. **The tools card hid its own checkboxes.** With every summarize tool unchecked,
   the card rendered the reason and no rows — so the setting could be turned off
   once and never back on, and the summarize feature was unrecoverable from the UI.
   Found while trying to re-check one tool after the R6 check. The rows now always
   render when the registry loaded, with the reason above them.
2. **The row's first copy listed its settings.** "New thread, fetch and search on,
   sent as soon as you tap" named two tools the user might well have unchecked — and
   on the device, with only Web Fetch enabled, it lied. See *Deviations*.
3. **A share staged by an image the app cannot read** takes the rejection path, not
   the image path, on a `content://` push from `am start` without a read grant — worth
   knowing before reading the R1 image row as a staged-image check.

### Outstanding — not exercised on device

| Feature | Requirement | Why outstanding |
|---------|-------------|-----------------|
| F16 | R5's `PUT`-failure notice | Needs the `PUT` to fail while the `POST` succeeds; from the client those two calls are indistinguishable, so the failure has to be injected server-side. Unit-covered end to end, including the exact notice text the screen renders |
| F16 | R1's staged-image half | `am start` with `--grant-read-uri-permission` on a MediaStore PNG still landed on the rejection path on this emulator. The rule itself is unit-tested against a staged image with a URL in its caption |
| F16 | R6 at 1.5× font scale, dark theme | Behaviour-irrelevant layout; the cards are the app's existing `Card`/`ToolRow` primitives |

