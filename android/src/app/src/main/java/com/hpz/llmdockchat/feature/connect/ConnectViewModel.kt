package com.hpz.llmdockchat.feature.connect

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.auth.SessionManager
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.core.net.ServerUrlStore
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.data.Reachability
import com.hpz.llmdockchat.data.ReachabilityRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class LoginMethod { PASSWORD, CODE }

data class ConnectUiState(
    val address: String = "",
    val addressError: String? = null,
    val method: LoginMethod = LoginMethod.PASSWORD,
    val password: String = "",
    val passwordVisible: Boolean = false,
    val code: String = "",
    val busy: Boolean = false,
    /** A failed attempt, in the dashboard's own words wherever it supplied any. */
    val failure: String? = null,
    /** Why the app came back here — a rejected credential, an ended session. */
    val notice: String? = null,
    val signedIn: Boolean = false,
) {
    val canSubmit: Boolean
        get() = !busy && address.isNotBlank() && when (method) {
            LoginMethod.PASSWORD -> password.isNotEmpty()
            LoginMethod.CODE -> code.length == CODE_LENGTH
        }
}

const val CODE_LENGTH = 6

class ConnectViewModel(
    private val sessionManager: SessionManager,
    private val reachability: ReachabilityRepository,
    private val serverUrlStore: ServerUrlStore,
    sessionState: SessionState,
) : ViewModel() {

    private val _state = MutableStateFlow(ConnectUiState(notice = sessionState.reason.value))
    val state: StateFlow<ConnectUiState> = _state.asStateFlow()

    init {
        // Prefilled on every later visit (F01-R1), including after a sign-out,
        // which keeps the address on purpose.
        viewModelScope.launch {
            serverUrlStore.baseUrl.collect { stored ->
                val saved = (stored as? Stored.Ready)?.value?.value ?: return@collect
                _state.value = _state.value.let {
                    if (it.address.isBlank()) it.copy(address = saved) else it
                }
            }
        }
    }

    fun onAddressChange(value: String) {
        _state.value = _state.value.copy(address = value, addressError = null, failure = null)
    }

    fun onMethodChange(method: LoginMethod) {
        _state.value = _state.value.copy(method = method, failure = null)
    }

    fun onPasswordChange(value: String) {
        _state.value = _state.value.copy(password = value, failure = null)
    }

    fun onPasswordVisibilityToggle() {
        _state.value = _state.value.copy(passwordVisible = !_state.value.passwordVisible)
    }

    /**
     * Six digits and nothing else. Submitting on the sixth (F01-R3) removes the
     * button press that a code with a 30-second life cannot afford.
     */
    fun onCodeChange(value: String) {
        val digits = value.filter(Char::isDigit).take(CODE_LENGTH)
        _state.value = _state.value.copy(code = digits, failure = null)
        if (digits.length == CODE_LENGTH && !_state.value.busy) submit()
    }

    fun submit() {
        val current = _state.value
        if (current.busy) return

        // Rejected inline, before anything reaches the network (F01-R1).
        val server = when (val parsed = BaseUrl.normalize(current.address)) {
            is BaseUrlResult.Invalid -> {
                _state.value = current.copy(addressError = parsed.reason)
                return
            }
            is BaseUrlResult.Valid -> parsed.baseUrl
        }

        _state.value = current.copy(busy = true, failure = null, notice = null, addressError = null)
        viewModelScope.launch {
            // The address has to be stored before the probe: every request is
            // built from it (F00-R1), so there is nowhere else to read it from.
            serverUrlStore.set(server)

            when (val reach = reachability.probe()) {
                Reachability.Dashboard -> Unit
                is Reachability.Unreachable -> return@launch fail(
                    "Could not reach a server at ${server.value}. ${reach.detail}".trim(),
                )
                Reachability.NotADashboard -> return@launch fail(
                    "${server.value} answered, but it is not an llm-dock dashboard.",
                )
            }

            val result = when (current.method) {
                LoginMethod.PASSWORD -> sessionManager.signInWithPassword(server, current.password)
                LoginMethod.CODE -> sessionManager.signInWithTotpCode(server, current.code)
            }

            result.fold(
                onSuccess = { _state.value = _state.value.copy(busy = false, signedIn = true) },
                onFailure = { fail(it.appError.displayMessage) },
            )
        }
    }

    /**
     * The address is left exactly as typed, and so is the method — only the
     * secret is cleared, so the next attempt starts from an empty code or an
     * empty password rather than from a stale one (F01-R3, F01-R4).
     */
    private fun fail(message: String) {
        _state.value = _state.value.copy(busy = false, failure = message, code = "")
    }
}
