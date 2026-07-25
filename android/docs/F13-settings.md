# F13 · Settings

**Mockup:** screen 09 · Settings · **Depends on:** F01

Short on purpose. Anything that belongs to the server stays on the
dashboard; the phone only holds what is about this phone.

---

## F13-R1 · Server and session (Must)

Shows the configured server address and the session state, with a sign
out that actually clears the token (F01-R7). Changing the address
re-authenticates.

**Acceptance criteria**

- [ ] The current address is shown and editable.
- [ ] Changing it requires a fresh login before any authenticated call.
- [ ] Sign out returns to Connect and no authenticated call succeeds
      afterwards.
- [ ] A connection test is available and distinguishes unreachable from
      unauthenticated.

## F13-R2 · Text size (Must)

The one accessibility knob that matters when reading model output on a
phone in bed. Applies to message bodies (F00-R8).

**Acceptance criteria**

- [ ] The control changes message text size immediately and the setting
      survives a restart.
- [ ] It composes with the device font scale rather than fighting it.

## F13-R3 · Serif toggle (Should)

Assistant prose in serif is the default (F05-R4). Some people hate serif
on phones; this switches it to sans.

**Acceptance criteria**

- [ ] Toggling changes assistant prose only, not code blocks or the
      user's own messages, and persists.

## F13-R4 · Defaults for new chats (Should)

Remembered model, prompt and tool selection for the new-chat sheet
(F03). Only worth a settings row if the sheet keeps more than the model.

**Acceptance criteria**

- [ ] Defaults shown here match what the new-chat sheet prefills.
- [ ] Clearing a default makes the sheet ask on the next new chat.

## F13-R5 · Keep the screen on while generating (Should)

Nice for watching a long answer; costs battery, so it is off by default.

**Acceptance criteria**

- [ ] With it on, the screen stays awake for the duration of a run and
      releases immediately afterwards — including when the run fails or
      is cancelled.
- [ ] With it off, normal screen timeout applies.

## F13-R6 · About (Should)

App version, and the dashboard's version and health from
`GET /api/health` (`status`, `version`, `docker_available`,
`nvidia_available`).

**Acceptance criteria**

- [ ] Shows the app version and the connected server's reported health.
- [ ] Renders sensibly when the server is unreachable.

## F13-R7 · Nothing server-side is editable here (Must)

The default system prompt, the OpenRouter model list and the MCP registry
are all server settings with working endpoints. The phone reads them
where it needs them and never writes them (F00-R10).

**Acceptance criteria**

- [ ] Settings contains no control that writes to `/api/chat/settings/*`
      or `/api/chat/mcp-registry/*`.

---

## Endpoints used

| Method | Path |
|---|---|
| GET | `/api/health` |
| POST | `/api/auth/verify` |

## Deviations from the mockup

None. Screen 09 already scopes settings to the phone.

## Out of scope

- A manual theme switch. The app follows the system theme (F00-R7); there
  is no in-app light/dark override in v1.
- Notification preferences — there are no notifications (F09-R6).
- GPU monitor, container control, benchmarks, project files. Screen 09
  lists these as explicit non-goals for settings; container control lives
  on its own tab (F10, F11), the rest are not in the app at all.
