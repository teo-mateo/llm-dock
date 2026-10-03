package com.hpz.llmdockchat.feature.account

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.auth.SessionManager
import com.hpz.llmdockchat.core.net.ServerUrlStore
import com.hpz.llmdockchat.core.prefs.Stored
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class AccountUiState(
    val server: String? = null,
)

/**
 * The signed-in account screen: which server, and the way out.
 *
 * [signOut] delegates and stops there. Routing is the app shell's one
 * `authenticationRequired` collector, so a second screen cannot disagree about
 * what signing out means — and the back stack it clears is the same one every
 * other lost-session path already clears.
 */
class AccountViewModel(
    private val sessionManager: SessionManager,
    serverUrlStore: ServerUrlStore,
) : ViewModel() {

    private val _state = MutableStateFlow(AccountUiState())
    val state: StateFlow<AccountUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            serverUrlStore.baseUrl.collect { stored ->
                _state.value = AccountUiState(server = (stored as? Stored.Ready)?.value?.value)
            }
        }
    }

    fun signOut() = sessionManager.signOut()
}
