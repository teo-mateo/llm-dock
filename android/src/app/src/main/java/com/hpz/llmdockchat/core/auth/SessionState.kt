package com.hpz.llmdockchat.core.auth

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * App-wide "the session is gone" signal (F00-R3, narrowed by F01-R6). The HTTP
 * stack raises it; the app shell observes it and routes to Connect.
 *
 * Under F01 an ordinary 401 no longer reaches here — silent re-auth absorbs it.
 * This fires only when re-authentication itself cannot succeed: no stored
 * credential, or one the dashboard rejects.
 *
 * Deliberately a [StateFlow] rather than an event stream: a signal raised while
 * nothing is collecting must still be visible to whatever collects next.
 */
class SessionState {

    private val _authenticationRequired = MutableStateFlow(false)
    val authenticationRequired: StateFlow<Boolean> = _authenticationRequired.asStateFlow()

    private val _reason = MutableStateFlow<String?>(null)

    /**
     * Why Connect is being shown, when there is something worth saying —
     * F01-R6 requires the app to explain a rejected credential rather than
     * silently reappearing at the login screen. Null after a plain sign-out.
     */
    val reason: StateFlow<String?> = _reason.asStateFlow()

    /**
     * A null [reason] leaves any reason already set alone. The re-authenticator
     * knows *why* the session is unrecoverable; the HTTP stack that raises the
     * signal a moment later does not, and must not overwrite it with silence.
     */
    fun requireAuthentication(reason: String? = null) {
        if (reason != null) _reason.value = reason
        _authenticationRequired.value = true
    }

    fun authenticated() {
        _reason.value = null
        _authenticationRequired.value = false
    }

    /** Sign-out (F01-R7): back to Connect, with nothing to explain. */
    fun signedOut() {
        _reason.value = null
        _authenticationRequired.value = true
    }
}
