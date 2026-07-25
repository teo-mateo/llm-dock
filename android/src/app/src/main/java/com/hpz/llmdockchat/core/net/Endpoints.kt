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

    /** F02 — the conversation list and its deletes. */
    const val CONVERSATIONS = "/api/chat/conversations"
    const val CONVERSATIONS_DELETE_BATCH = "/api/chat/conversations/delete"
    fun conversation(id: String): String = "/api/chat/conversations/$id"

    /** F04 — sending a turn, stopping it, and reattaching to it. */
    fun conversationMessages(id: String): String = "${conversation(id)}/messages"
    fun conversationMessage(id: String, messageId: String): String = "${conversation(id)}/messages/$messageId"
    fun cancelActiveRun(id: String): String = "${conversation(id)}/cancel-active-run"
    fun runStream(runId: String): String = "/api/chat/runs/$runId/stream"

    /** F03 — sources for the new-chat sheet's model/prompt/tools rows. */
    const val SERVICES = "/api/services"
    const val PROMPTS = "/api/chat/prompts"
    const val MCP_SERVERS = "/api/chat/mcp-servers"

    /** Read-only from the phone (F03) — editing the curated list is desktop Tools-page work. */
    const val OPENROUTER_MODELS_SETTINGS = "/api/chat/settings/openrouter-models"

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
