package com.hpz.llmdockchat.feature.conversations

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
 * F00-R5's four states, plus the two things F02 layers on top of "populated":
 * a background [refreshing] flag (F02-R1's fourth criterion — no full-screen
 * spinner over already-loaded content) and multi-select (F02-R5).
 */
sealed interface ConversationListUiState {
    data object Loading : ConversationListUiState

    data class Loaded(
        val conversations: List<ConversationSummary>,
        val refreshing: Boolean = false,
        val selection: Set<String> = emptySet(),
        /** A delete that failed — surfaced once, not swallowed (F00-R4). */
        val actionError: String? = null,
    ) : ConversationListUiState {
        val isEmpty: Boolean get() = conversations.isEmpty()
        val selectionMode: Boolean get() = selection.isNotEmpty()
    }

    data class Failed(val message: String) : ConversationListUiState
}

class ConversationListViewModel(
    private val repository: ConversationsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<ConversationListUiState>(ConversationListUiState.Loading)
    val state: StateFlow<ConversationListUiState> = _state.asStateFlow()

    /**
     * Not called from `init`: the screen's own `LaunchedEffect(Unit)` is what
     * triggers the first load, and it fires again every time the composable
     * re-enters composition (tab switch, back from a thread) — see
     * [ConversationListScreen]. Calling [refresh] here too would race a
     * second, redundant request against that first one.
     *
     * Called on first load, on explicit retry, and every time the list screen
     * is returned to (F02-R1). Already-loaded content stays on screen while a
     * refresh is in flight — only a cold start or a retry-from-failure shows
     * the full loading state.
     */
    fun refresh() {
        val current = _state.value
        _state.value = when (current) {
            is ConversationListUiState.Loaded -> current.copy(refreshing = true, actionError = null)
            else -> ConversationListUiState.Loading
        }
        viewModelScope.launch {
            repository.list().fold(
                onSuccess = { conversations ->
                    val selection = (current as? ConversationListUiState.Loaded)?.selection.orEmpty()
                        .intersect(conversations.map { it.id }.toSet())
                    _state.value = ConversationListUiState.Loaded(
                        conversations = conversations,
                        selection = selection,
                    )
                },
                onFailure = { failure ->
                    _state.value = ConversationListUiState.Failed(failure.appError.displayMessage)
                },
            )
        }
    }

    fun delete(id: String) {
        viewModelScope.launch {
            repository.delete(id).fold(
                onSuccess = { refresh() },
                onFailure = { failure -> reportActionFailure(failure.appError.displayMessage) },
            )
        }
    }

    fun deleteSelected() {
        val ids = (_state.value as? ConversationListUiState.Loaded)?.selection?.toList().orEmpty()
        if (ids.isEmpty()) return
        viewModelScope.launch {
            repository.deleteMany(ids).fold(
                onSuccess = { refresh() },
                onFailure = { failure -> reportActionFailure(failure.appError.displayMessage) },
            )
        }
    }

    fun enterSelection(id: String) = updateLoaded { it.copy(selection = setOf(id)) }

    fun toggleSelection(id: String) = updateLoaded {
        val selection = if (id in it.selection) it.selection - id else it.selection + id
        it.copy(selection = selection)
    }

    fun clearSelection() = updateLoaded { it.copy(selection = emptySet()) }

    private fun reportActionFailure(message: String) = updateLoaded {
        it.copy(refreshing = false, actionError = message)
    }

    private inline fun updateLoaded(transform: (ConversationListUiState.Loaded) -> ConversationListUiState.Loaded) {
        val current = _state.value
        if (current is ConversationListUiState.Loaded) _state.value = transform(current)
    }
}
