# F01 · Connection and authentication

**Mockup:** screen 01 · Connect · **Depends on:** F00 · **Blocks:** everything

Getting in, staying in, and getting back in after the server restarts.

---

## Correction to the mockups

`docs/android/README.md` and the screen-01 notes say login is
`POST /api/totp/verify`. **That is wrong.** `/api/totp/verify` is TOTP
*enrollment* — it requires an existing valid token, and it writes the
secret to the server's config. It cannot be used to sign in.

The real flow, as used by the web UI:

```
POST /api/auth/login
X-TOTP-Code: 123456
(no body)
→ 200 {"token": "totp-…", "expires_in": 28800}
→ 400 if the header is missing or TOTP is not configured server-side
→ 401 {"error": "Invalid TOTP code"}
```

Everything else about screen 01 stands.

---

## F01-R1 · Server address (Must)

The first screen asks for the dashboard address. It is stored and
prefilled on every later visit. The same app must work on the LAN and
through the reverse proxy, so the field takes a full origin including
scheme and optional port.

**Acceptance criteria**

- [ ] The address persists across app restarts and is prefilled.
- [ ] `http://10.0.2.2:3399`, `http://192.168.x.x:3399` and
      `https://host.example` are all accepted.
- [ ] A malformed address is rejected inline before any request is made.

## F01-R2 · Reachability check before login (Should)

Before asking for a code, the app can confirm the address points at a
dashboard by calling `GET /api/health`, which needs no auth. This
separates "wrong address" from "wrong code" — the two failures a user
cannot otherwise tell apart.

**Acceptance criteria**

- [ ] A wrong host reports that the server was unreachable, and does not
      ask for a TOTP code.
- [ ] A reachable host that is not a dashboard (200 without the expected
      payload) is reported as such.
- [ ] The check never blocks login for longer than a few seconds.

## F01-R3 · TOTP login (Must)

A six-digit code is entered and sent as `X-TOTP-Code` on
`POST /api/auth/login`. The returned `token` becomes the session token
and `expires_in` (28800 s) is its lifetime.

**Acceptance criteria**

- [ ] A valid code signs in and lands on the conversation list.
- [ ] An invalid code shows the server's message and leaves the field
      ready for another attempt, with the address untouched.
- [ ] The input accepts exactly six digits, offers a numeric keyboard,
      and submits without needing a separate button press once complete.
- [ ] A code that expires mid-typing (30 s window) fails with the same
      clear message, not a crash.

## F01-R4 · Password login (Must)

The dashboard's other way in, and the one the legacy login page presents
first. What that page calls a "password" **is** `DASHBOARD_TOKEN` from
`dashboard/.env`: the page POSTs it as a bearer to
`POST /api/auth/session`, which returns the same `{token, expires_in}`
session as a TOTP login.

```
POST /api/auth/session
Authorization: Bearer <password>
→ 200 {"token": "totp-…", "expires_in": 28800}
→ 401 {"error": "Invalid token"}
```

Both paths are first-class on the phone: TOTP (F01-R3) and password. The
Connect screen offers both, as the web login page does.

**Acceptance criteria**

- [ ] A valid password signs in and lands on the conversation list.
- [ ] An invalid password reports the failure and leaves the field ready
      for another attempt, with the address untouched.
- [ ] The field is masked, with a reveal toggle.
- [ ] Both login methods are reachable from the Connect screen without
      digging through a menu.

## F01-R5 · Credential storage (Must)

Two things are stored, both encrypted at rest, never in plain
preferences: the current session token, and — to satisfy F01-R6 — the
credential that produced it (the password, or the TOTP secret if the user
chooses to store it).

**This is a deliberate trade-off.** Staying signed in forever means the
phone holds a working dashboard credential, not just an 8 h token. A lost
unlocked phone is then a lost dashboard password. Encrypted storage is
the floor; the biometric gate in F01-R8 is what actually mitigates it,
and it is worth more under this requirement than it was before.

**Acceptance criteria**

- [ ] Neither the session token nor the stored credential is readable in
      plaintext from the app's data directory on a rooted or debuggable
      device.
- [ ] Clearing app data removes both.
- [ ] Sign out removes both (F01-R7).
- [ ] The stored credential never appears in a log line or a crash report.

## F01-R6 · Signed in until signed out (Must)

Once authenticated, the app stays authenticated. The user sees the
Connect screen again only after an explicit sign-out.

The server cannot deliver this on its own: sessions idle-expire after 8 h
and every token dies when the dashboard restarts. So the app re-obtains a
session **silently**, using the stored credential (F01-R5), whenever the
current one stops working. The user is never asked to re-authenticate as
a matter of routine.

This supersedes the plain 401-to-Connect behaviour in F00-R3: Connect is
reached only when silent re-auth itself fails — a changed password, a
revoked or reconfigured TOTP secret.

**Acceptance criteria**

- [ ] After a week of not opening the app, opening it works with no
      login prompt.
- [ ] Restarting the dashboard mid-session does not present a login
      prompt; the next action succeeds after a transparent re-auth.
- [ ] A 401 during a streaming turn re-authenticates and the turn is
      recoverable — the user's message is not lost.
- [ ] Silent re-auth is attempted at most a bounded number of times
      before falling back to Connect; it never loops on a permanently
      bad credential.
- [ ] When the stored credential is genuinely rejected, the app goes to
      Connect and says why.
- [ ] TOTP-only users, who have no storable credential unless they chose
      to save the secret, are told plainly that they will be asked for a
      code again — this requirement is only fully deliverable for the
      password path and for a stored TOTP secret.

## F01-R7 · Sign out (Must)

Sign out clears the stored token and returns to Connect. The server
address is kept.

**Acceptance criteria**

- [ ] After sign-out, no authenticated request succeeds until a new code
      is entered.
- [ ] The address field is still prefilled.

## F01-R8 · Biometric gate (Later)

A fingerprint or face prompt in front of the stored token, so a found
phone is not a signed-in dashboard.

Not in v1. Recorded because the mockup raises it and the answer is "not
yet", not "no".

---

## Endpoints used

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | Unauthenticated |
| POST | `/api/auth/login` | `X-TOTP-Code` header, no body |
| POST | `/api/auth/session` | Static-token exchange (F01-R4) |
| POST | `/api/auth/verify` | Optional token liveness probe |

## Out of scope

- TOTP enrollment or QR provisioning (`/api/totp/setup`, `/api/totp/verify`).
  The phone consumes an already-configured secret; enrollment is
  dashboard work.
- Disabling TOTP server-side.
- Multiple saved servers. One address at a time.
