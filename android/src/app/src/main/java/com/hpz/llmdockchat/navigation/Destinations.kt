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

    /** F02-R8's primary action, built out in F03. */
    const val NEW_CHAT = "new_chat"
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
