package com.hpz.llmdockchat.core.auth

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * App-wide "the session is gone" signal (F00-R3). The HTTP stack raises it;
 * the app shell observes it and routes to Connect (F01).
 *
 * Deliberately a [StateFlow] rather than an event stream: a 401 raised while
 * nothing is collecting must still be visible to whatever collects next.
 */
class SessionState {

    private val _authenticationRequired = MutableStateFlow(false)
    val authenticationRequired: StateFlow<Boolean> = _authenticationRequired.asStateFlow()

    fun requireAuthentication() {
        _authenticationRequired.value = true
    }

    fun authenticated() {
        _authenticationRequired.value = false
    }
}
