package com.hpz.llmdockchat.core.net

import okhttp3.Request

/**
 * Paths, never URLs — the host comes from [BaseUrl] at call time (F00-R1).
 * Only what F00 needs; later features add their own.
 */
object Endpoints {
    const val HEALTH = "/api/health"

    /** F01 uses these; named here because the HTTP stack has to know about them. */
    const val AUTH_LOGIN = "/api/auth/login"
    const val AUTH_SESSION = "/api/auth/session"

    /** Authenticated, unlike the two above — it is a probe, not a way in. */
    const val AUTH_VERIFY = "/api/auth/verify"

    /**
     * Requests that establish a session, and so cannot depend on one.
     *
     * Neither login route is decorated with `require_auth` in
     * `dashboard/routes/system.py`: `/api/auth/login` authenticates with an
     * `X-TOTP-Code` header and `/api/auth/session` with the dashboard password
     * as its bearer. Attaching a session token to them, requiring one before
     * they may be sent, or re-authenticating when one comes back 401 would each
     * make signing in impossible.
     */
    fun establishesSession(request: Request): Boolean {
        val path = request.url.encodedPath.trimEnd('/')
        return when {
            request.method == "GET" && path.endsWith(HEALTH) -> true
            request.method == "POST" && path.endsWith(AUTH_LOGIN) -> true
            request.method == "POST" && path.endsWith(AUTH_SESSION) -> true
            else -> false
        }
    }
}
