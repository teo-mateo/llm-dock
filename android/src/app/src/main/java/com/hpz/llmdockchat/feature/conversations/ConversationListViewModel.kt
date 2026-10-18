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
 * The four UI states, plus the two things the list layers on top of
  * "populated": a background [refreshing] flag (no full-screen spinner over
  * already-loaded content) and multi-select.
 */
sealed interface ConversationListUiState {
    data object Loading : ConversationListUiState

    data class Loaded(
        val conversations: List<ConversationSummary>,
        val refreshing: Boolean = false,
        val selection: Set<String> = emptySet(),
        /** A delete that failed — surfaced once, not swallowed. */
        val actionError: String? = null,
        /**
         * Swiped away but not yet deleted on the server. Held here rather than
         * removed from [conversations] so a refresh landing inside the undo
         * window cannot resurrect the row.
         */
        val pendingUndo: PendingUndo? = null,
        /**
         * Rows whose DELETE is in flight, past the undo window. Kept apart from
         * [pendingUndo] because the row must stay hidden even after the snackbar
         * is gone: the server lists it until the delete lands, and a refresh
         * arriving in between would put a row back that is already being deleted.
         */
        val pendingDeletion: Set<String> = emptySet(),
        /**
         * Rows this screen has already deleted successfully. A list response
         * fetched before the DELETE landed still contains them, and the server
         * will never hand those ids out again, so such a row is not news — it is
         * a stale snapshot of a conversation that is gone.
         */
        val deletedIds: Set<String> = emptySet(),
    ) : ConversationListUiState {
        /** What the list draws: swiped and mid-deletion rows are gone from it. */
        val visible: List<ConversationSummary>
            get() = conversations.filterNot {
                it.id == pendingUndo?.id || it.id in pendingDeletion || it.id in deletedIds
            }

        val isEmpty: Boolean get() = visible.isEmpty()
        val selectionMode: Boolean get() = selection.isNotEmpty()
    }

    /** A delete waiting out its undo window. */
    data class PendingUndo(val id: String, val title: String)

    data class Failed(val message: String) : ConversationListUiState
}

class ConversationListViewModel(
    private val repository: ConversationsRepository,
    private val undoWindowMs: Long = UNDO_WINDOW_MS,
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
     * is returned to. Already-loaded content stays on screen while a
     * refresh is in flight — only a cold start or a retry-from-failure shows
     * the full loading state.
     */
    fun refresh() {
        val generation = ++refreshGeneration
        _state.value = when (val current = _state.value) {
            is ConversationListUiState.Loaded -> current.copy(refreshing = true, actionError = null)
            else -> ConversationListUiState.Loading
        }
        viewModelScope.launch {
            repository.list().fold(
                onSuccess = { conversations -> applyRefresh(generation, conversations) },
                onFailure = { failure ->
                    if (generation == refreshGeneration) {
                        _state.value = ConversationListUiState.Failed(failure.appError.displayMessage)
                    }
                },
            )
        }
    }

    /**
     * A response replaces the rows and nothing else. The undo, the mid-deletion
     * set and the selection are read from the state as it is *now*, not from the
     * state as it was when the request left: a swipe or a selection tap that
     * happened while this request was in flight would otherwise be rolled back to
     * its pre-request value, which pops the swiped row back into the list while
     * its still-running deletion timer goes on to delete it behind a snackbar
     * that has already disappeared.
     *
     * A superseded response writes nothing at all, so an older refresh cannot
     * overwrite a newer one's rows, undo, or error.
     */
    private fun applyRefresh(generation: Int, conversations: List<ConversationSummary>) {
        if (generation != refreshGeneration) return
        val latest = _state.value as? ConversationListUiState.Loaded
        val alreadyGone = latest?.deletedIds.orEmpty()
        val rows = conversations.filterNot { it.id in alreadyGone }
        _state.value = ConversationListUiState.Loaded(
            conversations = rows,
            selection = latest?.selection?.intersect(rows.map { it.id }.toSet()).orEmpty(),
            pendingUndo = latest?.pendingUndo,
            pendingDeletion = latest?.pendingDeletion.orEmpty(),
            deletedIds = alreadyGone,
        )
    }

    /**
     * Confirm-then-delete, still used by the multi-select bar's single-row
     * path. A swipe goes through [deleteWithUndo] instead.
     */
    fun delete(id: String) {
        viewModelScope.launch {
            repository.delete(id).fold(
                onSuccess = {
                    markDeleted(listOf(id))
                    refresh()
                },
                onFailure = { failure -> reportActionFailure(failure.appError.displayMessage) },
            )
        }
    }

    /**
     * Records deletes that landed, so the refresh that follows one — which may
     * have been fetched before the server acted — cannot put the row back. The
     * ids leave the selection with them: a selection that still names deleted
     * rows offers an action on nothing.
     */
    private fun markDeleted(ids: List<String>) = updateLoaded {
        it.copy(deletedIds = it.deletedIds + ids, selection = it.selection - ids.toSet())
    }

    private var undoJob: Job? = null

    /** Only the newest refresh may write the state; see [applyRefresh]. */
    private var refreshGeneration = 0

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
            delay(undoWindowMs)
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
        val loaded = _state.value as? ConversationListUiState.Loaded ?: return
        val pending = loaded.pendingUndo ?: return
        undoJob?.cancel()
        undoJob = null
        // Its DELETE is already open. Sending a second one would earn a 404 for a
        // conversation the user has deleted exactly once, and the error would read
        // as if their swipe had failed.
        if (pending.id in loaded.pendingDeletion) return
        viewModelScope.launch { commitPending(pending.id) }
    }

    private suspend fun commitPending(id: String) {
        updateLoaded { it.copy(pendingDeletion = it.pendingDeletion + id) }
        repository.delete(id).fold(
            onSuccess = {
                updateLoaded {
                    it.copy(
                        conversations = it.conversations.filterNot { row -> row.id == id },
                        pendingUndo = it.pendingUndo?.takeIf { pending -> pending.id != id },
                        pendingDeletion = it.pendingDeletion - id,
                        deletedIds = it.deletedIds + id,
                    )
                }
            },
            onFailure = { failure ->
                // The row comes back: it still exists on the server, and
                // leaving it hidden would be the UI lying about what is there.
                updateLoaded {
                    it.copy(
                        pendingUndo = it.pendingUndo?.takeIf { pending -> pending.id != id },
                        pendingDeletion = it.pendingDeletion - id,
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
                onSuccess = {
                    markDeleted(ids)
                    refresh()
                },
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
