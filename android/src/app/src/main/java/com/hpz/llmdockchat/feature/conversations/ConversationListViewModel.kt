package com.hpz.llmdockchat.feature.conversations

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.model.ConversationSummary
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
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
        /**
         * Swiped away but not yet deleted on the server. Held here rather than
         * removed from [conversations] so a refresh landing inside the undo
         * window cannot resurrect the row.
         */
        val pendingUndo: PendingUndo? = null,
    ) : ConversationListUiState {
        /** What the list draws: the pending row is already gone from it. */
        val visible: List<ConversationSummary>
            get() = pendingUndo?.let { pending -> conversations.filterNot { it.id == pending.id } }
                ?: conversations

        val isEmpty: Boolean get() = visible.isEmpty()
        val selectionMode: Boolean get() = selection.isNotEmpty()
    }

    /** A delete waiting out its undo window. */
    data class PendingUndo(val id: String, val title: String)

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
                    val loaded = current as? ConversationListUiState.Loaded
                    val selection = loaded?.selection.orEmpty()
                        .intersect(conversations.map { it.id }.toSet())
                    _state.value = ConversationListUiState.Loaded(
                        conversations = conversations,
                        selection = selection,
                        // Carried across: the server still has this row, so a
                        // refresh mid-window would otherwise pop it back.
                        pendingUndo = loaded?.pendingUndo,
                    )
                },
                onFailure = { failure ->
                    _state.value = ConversationListUiState.Failed(failure.appError.displayMessage)
                },
            )
        }
    }

    /**
     * Confirm-then-delete, still used by the multi-select bar's single-row
     * path. A swipe goes through [deleteWithUndo] instead.
     */
    fun delete(id: String) {
        viewModelScope.launch {
            repository.delete(id).fold(
                onSuccess = { refresh() },
                onFailure = { failure -> reportActionFailure(failure.appError.displayMessage) },
            )
        }
    }

    private var undoJob: Job? = null

    /**
     * Swipe-to-delete with an undo window instead of a confirm dialog.
     *
     * The row leaves the list at once and the request is held for
     * [UNDO_WINDOW_MS]; only when that expires is anything sent to the server,
     * so an undo costs nothing and needs no second call to put the thread back.
     * That is also why this cannot use an optimistic delete plus a re-create —
     * the server assigns ids, and a re-created thread would not be the same
     * conversation.
     *
     * A second swipe inside the window commits the first immediately rather
     * than dropping it: the alternative is silently keeping a thread the user
     * has already swiped away.
     */
    fun deleteWithUndo(item: ConversationSummary) {
        commitPendingNow()
        updateLoaded { it.copy(pendingUndo = ConversationListUiState.PendingUndo(item.id, item.title)) }
        undoJob = viewModelScope.launch {
            delay(UNDO_WINDOW_MS)
            commitPending(item.id)
        }
    }

    fun undoDelete() {
        undoJob?.cancel()
        undoJob = null
        updateLoaded { it.copy(pendingUndo = null) }
    }

    /** Commits without waiting — used when a second swipe arrives, and on clear-down. */
    private fun commitPendingNow() {
        val pending = (_state.value as? ConversationListUiState.Loaded)?.pendingUndo ?: return
        undoJob?.cancel()
        undoJob = null
        viewModelScope.launch { commitPending(pending.id) }
    }

    private suspend fun commitPending(id: String) {
        repository.delete(id).fold(
            onSuccess = {
                updateLoaded {
                    it.copy(
                        conversations = it.conversations.filterNot { row -> row.id == id },
                        pendingUndo = it.pendingUndo?.takeIf { pending -> pending.id != id },
                    )
                }
            },
            onFailure = { failure ->
                // The row comes back: it still exists on the server, and
                // leaving it hidden would be the UI lying about what is there.
                updateLoaded {
                    it.copy(
                        pendingUndo = it.pendingUndo?.takeIf { pending -> pending.id != id },
                        actionError = failure.appError.displayMessage,
                    )
                }
            },
        )
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

    private companion object {
        /** Long enough to read the snackbar and reach for it, short enough not to feel stuck. */
        const val UNDO_WINDOW_MS = 3_000L
    }

    private inline fun updateLoaded(transform: (ConversationListUiState.Loaded) -> ConversationListUiState.Loaded) {
        val current = _state.value
        if (current is ConversationListUiState.Loaded) _state.value = transform(current)
    }
}
