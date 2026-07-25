package com.hpz.llmdockchat.navigation

import com.hpz.llmdockchat.core.net.BaseUrl

/**
 * The app's destinations (Architecture D12). F01 has two; the two-tab scaffold
 * arrives with the list screens it is meant to switch between.
 */
object Destinations {
    const val CONNECT = "connect"
    const val HOME = "home"
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
        Destinations.HOME
    } else {
        Destinations.CONNECT
    }
