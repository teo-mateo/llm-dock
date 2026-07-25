package com.hpz.llmdockchat.navigation

import com.hpz.llmdockchat.core.net.BaseUrl

/**
 * The app's destinations (Architecture D12). F02 replaces F01's placeholder
 * Home screen with the two-tab scaffold: [CHATS] and [MODELS] carry the
 * bottom bar (F02-R7), [THREAD] and [NEW_CHAT] are pushed on top of it
 * without one.
 */
object Destinations {
    const val CONNECT = "connect"

    /** The nested graph both tabs live in; navigating to it lands on [CHATS]. */
    const val TABS = "tabs"
    const val CHATS = "chats"
    const val MODELS = "models"

    private const val THREAD_ROUTE = "thread"
    const val THREAD = "$THREAD_ROUTE/{conversationId}"
    fun thread(conversationId: String) = "$THREAD_ROUTE/$conversationId"

    /** F11 — pushed on top of [TABS] without the bottom bar, same as [THREAD]. */
    private const val MODEL_DETAIL_ROUTE = "model_detail"
    const val MODEL_DETAIL = "$MODEL_DETAIL_ROUTE/{serviceName}"
    fun modelDetail(serviceName: String) = "$MODEL_DETAIL_ROUTE/$serviceName"

    /**
     * F02-R8's primary action, built out in F03. [NEW_CHAT] is the route
     * *pattern* registered with `composable(...)` — it must be the string
     * passed there and to `popUpTo(...)`, never navigated to directly (its
     * `{service}` is a literal placeholder, not a real path segment). Callers
     * navigate with [newChat] (no preselected model, F02/F03's original path)
     * or [newChatWithService] (F10-R6 — the query argument is optional and
     * nullable, so [newChat]'s plain route still matches the same
     * destination with `service` defaulting to null).
     */
    private const val NEW_CHAT_ROUTE = "new_chat"
    const val NEW_CHAT = "$NEW_CHAT_ROUTE?service={service}"
    fun newChat() = NEW_CHAT_ROUTE
    fun newChatWithService(serviceName: String) = "$NEW_CHAT_ROUTE?service=$serviceName"
}

/**
 * Which screen the app opens on, decided once from what is on disk.
 *
 * A stored *credential* is enough on its own: it renews the session silently
 * (F01-R6), so a token that died while the app was closed is not a reason to
 * ask for anything. A stored *token* without a credential is also enough —
 * that is a TOTP sign-in, and the token is good until it is not, at which
 * point the first 401 routes to Connect with an explanation.
 */
fun startDestination(server: BaseUrl?, token: String?, hasCredential: Boolean): String =
    if (server != null && (!token.isNullOrBlank() || hasCredential)) {
        Destinations.TABS
    } else {
        Destinations.CONNECT
    }
