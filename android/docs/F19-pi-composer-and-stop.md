# F19 · Pi composer and Stop

**Mockup:** `../../docs/pi-remote/mockups/PhoneSession.dc.html` footer · **Depends on:** F18, #372 · **UI:** #376

The session screen gains a composer that sends a message and a Stop control. The dashboard owns the
run; the phone sends a command and renders the outcome. This completes the Pi remote controls without
changing the chat thread's `ComposerRow`.

---

## F19-R1 · Send and steer (Must)

The composer sends the draft to `POST /api/pi/sessions/<session_id>/<instance_id>/messages`.
An idle session starts a turn; a working session steers the current run. Whitespace-only drafts are
not sent.

**Acceptance criteria**

- [x] A non-empty draft is posted as `{"text": "..."}`.
- [ ] An idle session starts a turn and a working session steers it.
- [x] Whitespace-only input sends nothing.
- [x] The draft clears on `Done` and `Pending`.

## F19-R2 · Stop (Must)

A Stop control appears only while the session is working. It records the stop time before posting
to `/api/pi/sessions/<session_id>/<instance_id>/abort`, so a run that ends just after the user's Stop
is labelled `stopped`.

**Acceptance criteria**

- [ ] Stop is absent on idle and ended sessions.
- [x] Stop posts to the abort endpoint and is disabled while the request is in flight.
- [x] The stop timestamp is recorded before the abort call.
- [x] A run end within 30 s of the stop shows `stopped`.

## F19-R3 · Outcome texts and run-end labels (Must)

The phone uses the same texts as the web composer: `Sent — pi will pick it up`, `pi is offline`,
`Too many messages — wait a minute`, `The dashboard is busy — try again`,
`Message is empty or too long`, `pi could not run it (<error>)` and `Could not send`. A rejected
send keeps the draft and shows the reason under the composer.

A run-end notice reads `stopped` when it follows a user Stop by at most 30 s; otherwise it uses
`run completed`, `aborted` or `error`.

**Acceptance criteria**

- [x] Each outcome maps to the specified text.
- [x] `Done` has no notice; a rejection keeps the draft and sets the notice.
- [x] Run-end labels match the web rule.

## F19-R4 · Screen behaviour (Must)

The composer is a stateless row under the transcript, with the field label `Message to pi`,
placeholder `Message pi…` (or `Steer pi…` while working), Send (`Send`) and Stop (`Stop the run`).
It is IME-aware. An ended session shows `Session ended — read only` instead of the composer.
No chat-thread composer is changed.

**Acceptance criteria**

- [ ] The composer row renders under the transcript with the specified labels.
- [ ] Send and Stop icons use their specified content descriptions.
- [ ] The composer pads for the keyboard.
- [ ] Ended sessions show the read-only line.
- [x] `ComposerRow` is unchanged.

---

## Endpoints used

| Method | Path | Use |
|---|---|---|
| POST | `/api/pi/sessions/<session_id>/<instance_id>/messages` | Send or steer — body `{text}` |
| POST | `/api/pi/sessions/<session_id>/<instance_id>/abort` | Stop the current run |

HTTP 200 (with `ok`), 202, 409, 429, 503 and 400 are command outcomes, not transport exceptions.

## Verification notes

JVM: `PiCommandsRepositoryTest` covers the status outcomes and the posted body; `PiCommandTextsTest`
covers every message and the run-end rule; `PiSessionViewModelTest` additions cover draft clearing,
rejection notice, whitespace and stop timestamp/abort. `assembleDebug` builds.

Emulator: the running dashboard still answers `/api/pi/...` with 404 (no `llm-dock.service`
restart), so no live pi session — and therefore no session-screen composer — was reachable. The
screenshot `../../docs/pi-remote/screenshots/f19-pi-tab-reconnecting.png` shows the Pi tab with
`Reconnecting…` and no rows. AC5's session-screen/composer screenshot remains outstanding.
