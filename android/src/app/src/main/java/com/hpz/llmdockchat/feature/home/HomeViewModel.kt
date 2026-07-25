package com.hpz.llmdockchat.feature.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.auth.AuthService
import com.hpz.llmdockchat.core.auth.SessionManager
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.ServerUrlStore
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.prefs.Stored
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class HomeUiState(
    val server: String = "",
    val checking: Boolean = true,
    val sessionValid: Boolean = false,
    val failure: String? = null,
)

/**
 * The signed-in destination until F02 replaces it with the conversation list.
 *
 * It calls `POST /api/auth/verify` on entry, which is the only authenticated
 * endpoint F01 is allowed to touch. That is not decoration: it is what makes
 * silent re-auth observable — with a dead token stored, this request 401s, the
 * transport re-authenticates from the credential, and the screen still lands on
 * "session verified" without Connect appearing (F01-R6).
 */
class HomeViewModel(
    private val authService: AuthService,
    private val sessionManager: SessionManager,
    serverUrlStore: ServerUrlStore,
) : ViewModel() {

    private val _state = MutableStateFlow(HomeUiState())
    val state: StateFlow<HomeUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            serverUrlStore.baseUrl.collect { stored ->
                val value = (stored as? Stored.Ready)?.value?.value.orEmpty()
                _state.value = _state.value.copy(server = value)
            }
        }
        verify()
    }

    fun verify() {
        _state.value = _state.value.copy(checking = true, failure = null)
        viewModelScope.launch {
            authService.verify().fold(
                onSuccess = { valid ->
                    _state.value = _state.value.copy(checking = false, sessionValid = valid)
                },
                onFailure = { failure ->
                    _state.value = _state.value.copy(
                        checking = false,
                        sessionValid = false,
                        failure = failure.appError.displayMessage,
                    )
                },
            )
        }
    }

    fun signOut() = sessionManager.signOut()
}
