package com.hpz.llmdockchat.feature.share

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.model.ConversationSummary
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * F00-R5's four states, for the share-target picker (F14-R2). Same list data
 * as the Chats tab — `ConversationsRepository.list()` is already
 * `updated_at DESC` and `unfiled=true` — but no selection, swipe or delete:
 * the only action is picking a row.
 */
sealed interface ShareTargetUiState {
    data object Loading : ShareTargetUiState

    data class Loaded(
        val conversations: List<ConversationSummary>,
        val share: StagedShare,
        val refreshing: Boolean = false,
    ) : ShareTargetUiState {
        val isEmpty: Boolean get() = conversations.isEmpty()
    }

    data class Failed(val message: String) : ShareTargetUiState
}

class ShareTargetViewModel(
    private val repository: ConversationsRepository,
    private val store: SharedDraftStore,
) : ViewModel() {

    private val _state = MutableStateFlow<ShareTargetUiState>(ShareTargetUiState.Loading)
    val state: StateFlow<ShareTargetUiState> = _state.asStateFlow()

    init {
        // A second share arriving while the picker is open replaces the staged
        // content on screen — the NavHost does not re-navigate (already here),
        // so the store is the only channel the change comes through.
        viewModelScope.launch {
            store.pending.collect { share ->
                val current = _state.value
                if (current is ShareTargetUiState.Loaded) {
                    _state.value = current.copy(share = share ?: StagedShare())
                }
            }
        }
    }

    /** Same shape as the conversation list's refresh: cold start and retry show Loading, return shows a refresh. */
    fun refresh() {
        val current = _state.value
        _state.value = when (current) {
            is ShareTargetUiState.Loaded -> current.copy(refreshing = true)
            else -> ShareTargetUiState.Loading
        }
        viewModelScope.launch {
            repository.list().fold(
                onSuccess = { conversations ->
                    _state.value = ShareTargetUiState.Loaded(
                        conversations = conversations,
                        share = store.pending.value ?: StagedShare(),
                    )
                },
                onFailure = { failure ->
                    _state.value = ShareTargetUiState.Failed(failure.appError.displayMessage)
                },
            )
        }
    }
}
