# Login page and page guard (#496)

Before this change the dashboard served the whole app shell to anonymous visitors:
`GET /` returned `static/index.html` with every modal and all `static/js/*`, and the
login form was an overlay inside it. No data leaked (every API route is behind
`require_auth`), but an unauthenticated visitor should see a login page and nothing else.

The problem is that browser navigations never send `Authorization`, so the server could
not tell a logged-in page load from an anonymous one. The fix is one session cookie that
gates **HTML delivery only**; the API stays bearer-only.

## Decisions

### The cookie gates pages, not the API

`POST /api/auth/session` and `POST /api/auth/login` set `llm_dock_session` (the existing
opaque `totp-…` session token) with `Path=/`, `HttpOnly`, `SameSite=Strict`,
`Max-Age=28800` and `Secure` when the request is HTTPS (or when
`DASHBOARD_TRUST_PROXY_HEADERS` is enabled and the first `X-Forwarded-Proto` is `https`).

The API does not accept the cookie. Every web client already sends the bearer on every
fetch and SSE stream, so cookie-on-API would buy nothing and would create a CSRF surface
on writes. The cookie's job is narrower: a page navigation carries it, and the guard uses
it to choose which static document to serve.

`HttpOnly` protects the cookie copy only. The session token is also in
`localStorage['dashboard_token']` because the API is bearer-only and the v1 app, the v2
SPA and the benchmark page all send it as a header. An XSS that can read localStorage can
already act as the user, so the cookie adds no new exposure.

### Fail-closed guard

`dashboard/page_paths.py` owns the path vocabulary (`is_api_path`, `is_asset_path`,
`is_page_path`, `LOGIN_PATH`, `PUBLIC_PATHS`) and the pure decision (`PageAccess`,
`page_access`). `dashboard/auth.py` wires it into the request hooks:

```python
def page_access(path, *, authenticated):
    if is_api_path(path) or path in PUBLIC_PATHS: return ALLOW
    if authenticated: return ALLOW
    if is_asset_path(path): return UNAUTHORIZED
    return LOGIN
```

Every request outside `/api` and `/login` is guarded. A future page route is protected
automatically; a new public non-`/api` route must be added to `PUBLIC_PATHS` explicitly.
An anonymous `GET`/`HEAD` page request gets `200` with `static/login.html` served **in
place** at the requested URL (a deep link works after login without a redirect
parameter); an anonymous asset request or an anonymous non-`GET` request gets `401` with
`Cache-Control: no-store`. `OPTIONS` passes through so CORS preflight still works. Cookie
sliding stays `GET`/`HEAD` only. The guard runs before routing, so Flask's built-in
`/static` route is covered too.

`/login` is also a public route. It is the explicit entry for v1/v2 401 bounces and
bookmarks; the login page's `?redirect=` is honored only there, validated as same-origin
and not `/login`, falling back to `/v2`. In-place pages ignore `?redirect=` and reload.

### Sliding is narrow

The cookie is re-issued only when the request already carried that same session cookie.
That is the narrowest rule that keeps it alive while the SPA is used without navigating:
browser clients send it on same-origin `fetch` (the default `credentials: "same-origin"`),
while Android (no cookie jar) and scripts (no dashboard page requests) get no
`Set-Cookie`. A request with a different cookie token does not clobber the valid cookie.
The page guard slides on page loads. `touch_session()` owns validity + sliding;
`session_valid()` is the non-sliding check used by logout; `revoke_session()` owns removal.

### Logout is credential-gated

`POST /api/auth/logout` is public and idempotent. With a valid credential (static bearer,
session bearer, or valid session cookie) it revokes the token(s) and clears the cookie
with the same attributes and `Max-Age=0`. Without one it returns `204` and sets no cookie.
This closes a forced-logout CSRF: `SameSite` is enforced on send, not on set, so a
cross-site auto-submitted form could otherwise delete the victim's cookie. The token is
not revoked by such a request because it carries no credential.

### One login page

`dashboard/static/login.html` is self-contained: inline CSS/JS, no CDN, root-relative
`/api`, password and TOTP tabs. It stores the session token in
`localStorage['dashboard_token']` (the SPA needs it) and navigates. The v1 login modal is
deleted; the v1 app redirects to `/login` on a missing/invalid token or a 401, and the
benchmark page does the same. The v2 SPA's `handleAuthFailure` and `logout` point at
`/login`; `logout` revokes server-side before navigating.

### No Vite build change

The login page is outside the bundle; `base: '/v2/'` and the dist layout are unchanged.
The guard is Flask-only: the Vite dev server on `:5173` serves the SPA unguarded and the
SPA keeps using the bearer against `:3399`. `localStorage` is per-origin including port,
so dev already keeps its own token.

## Rejected alternatives

- **Cookie accepted by the API** (issue step 4's "may use either"): no client needs it, and
  it forces CSRF handling on writes.
- **A `PROTECTED_PAGES` allowlist**: drifts when a page is added; fail-closed does not.
- **`302` to `/login` for anonymous pages**: loses the requested URL and the `curl` body
  check; serving in place is simpler.
- **`401` for anonymous pages**: the acceptance asks for the login body, and
  `WWW-Authenticate` would be ambiguous.
- **`?login=1` instead of `/login`**: a query param every protected path must honor; a
  public route is explicit and bookmarkable.
- **A React login route**: the SPA bundle must not load before authentication, and the
  acceptance requires the bundle to answer `401`.
- **Trusting `X-Forwarded-Proto` unconditionally**: a client header becomes a security
  decision; the flag makes the trust boundary explicit.
- **Keeping the v1 modal as a fallback**: two owners of the login form.

## Tests

`tests/test_page_guard.py` covers anonymous pages (login body, no app markup), anonymous
assets (`401`), a valid cookie, expired/unknown cookies, bearer-only page requests,
`/api/health`, cookie-only API requests, `no-store`, the pure `page_access` table, and a
`url_map` contract that every non-`/api` GET route is guarded. `tests/test_auth_cookie.py`
covers the cookie attributes, `Secure` (HTTPS and the proxy flag), the narrow slide rule
(bearer with/without/foreign cookie), logout revocation and the credential-less
forced-logout regression. `tests/test_v2_routes.py` now logs in for its SPA tests and adds
the anonymous cases.

## Pre-existing, not fixed here

`CORS(app)` uses flask-cors defaults (`origins="*"`, `allow_headers="*"`,
`supports_credentials=False`), so any website can read the responses to its own
cross-origin requests, including a guessed-`Authorization` `POST /api/auth/session` (a
password oracle; there is no rate limiting) and the public `/api/health`. The cookie does
not widen this. An origin allowlist and login rate limiting are a separate issue.
