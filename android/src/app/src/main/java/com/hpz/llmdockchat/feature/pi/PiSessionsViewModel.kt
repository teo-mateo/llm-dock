package com.hpz.llmdockchat.feature.pi

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.data.PiSessionDeleteRepository
import com.hpz.llmdockchat.data.PiSessionsRepository
import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

sealed interface PiSessionsUiState {
    data object Loading : PiSessionsUiState

    data class Loaded(
        val live: List<PiSession>,
        val ended: List<PiSession>,
        val stale: Boolean,
        val actionError: String? = null,
        val pendingUndo: PendingUndo? = null,
    ) : PiSessionsUiState {
        val visibleLive: List<PiSession>
            get() = live.filterNot { it.key == pendingUndo?.key }

        val visibleEnded: List<PiSession>
            get() = ended.filterNot { it.key == pendingUndo?.key }

        val isEmpty: Boolean
            get() = visibleLive.isEmpty() && visibleEnded.isEmpty()
    }

    data class PendingUndo(val key: PiSessionKey, val label: String)
}

data class PiCacheLabels(
    val warning: String? = null,
    val sizes: Map<PiSessionKey, String> = emptyMap(),
)

internal fun piCacheLabels(usage: PiCacheUsage, sessions: List<PiSession>, cachedBytes: (PiSessionKey) -> Long?) =
    PiCacheLabels(
        warning = if (usage.overWarning) {
            "Pi cache uses ${formatCacheBytes(usage.totalBytes)} on this phone (warning above ${formatCacheBytes(usage.warningBytes)})"
        } else {
            null
        },
        sizes = sessions.mapNotNull { session -> cachedBytes(session.key)?.let { session.key to formatCacheBytes(it) } }.toMap(),
    )

fun List<PiSession>.splitByLive(): Pair<List<PiSession>, List<PiSession>> =
    filter { it.live } to filterNot { it.live }

internal class PiSessionsViewModel(
    private val repository: PiSessionsRepository,
    private val deleteRepository: PiSessionDeleteRepository,
    private val undoWindowMs: Long = UNDO_WINDOW_MS,
    cacheUsage: StateFlow<PiCacheUsage> = MutableStateFlow(PiCacheUsage()),
    cachedBytes: (PiCacheUsage, PiSessionKey) -> Long? = { _, _ -> null },
) : ViewModel() {
    private val _state = MutableStateFlow<PiSessionsUiState>(PiSessionsUiState.Loading)
    val state: StateFlow<PiSessionsUiState> = _state.asStateFlow()
    val cacheLabels: StateFlow<PiCacheLabels> = combine(_state, cacheUsage) { state, usage ->
        val sessions = (state as? PiSessionsUiState.Loaded)?.let { it.live + it.ended }.orEmpty()
        piCacheLabels(usage, sessions) { cachedBytes(usage, it) }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), PiCacheLabels())
    private var started = false
    private var undoJob: Job? = null

    fun start() {
        if (started) return
        started = true
        viewModelScope.launch {
            repository.streamWithStatus().collect { update ->
                val (live, ended) = update.sessions.splitByLive()
                _state.value = PiSessionsUiState.Loaded(
                    live = live,
                    ended = ended,
                    stale = update.stale,
                    pendingUndo = (_state.value as? PiSessionsUiState.Loaded)?.pendingUndo,
                )
            }
        }
    }

    fun deleteWithUndo(session: PiSession) {
        commitPendingNow()
        updateLoaded {
            it.copy(pendingUndo = PiSessionsUiState.PendingUndo(session.key, piSessionTitle(session)))
        }
        undoJob = viewModelScope.launch {
            delay(undoWindowMs)
            commitPending(session.key)
        }
    }

    fun undoDelete() {
        undoJob?.cancel()
        undoJob = null
        updateLoaded { it.copy(pendingUndo = null) }
    }

    private fun commitPendingNow() {
        val pending = (_state.value as? PiSessionsUiState.Loaded)?.pendingUndo ?: return
        undoJob?.cancel()
        undoJob = null
        viewModelScope.launch { commitPending(pending.key) }
    }

    private suspend fun commitPending(key: PiSessionKey) {
        deleteRepository.delete(key).fold(
            onSuccess = { clearPending(key) },
            onFailure = { failure ->
                updateLoaded {
                    it.copy(
                        pendingUndo = it.pendingUndo?.takeUnless { pending -> pending.key == key },
                        actionError = deleteFailureMessage(failure),
                    )
                }
            },
        )
    }

    private fun clearPending(key: PiSessionKey) {
        updateLoaded { it.copy(pendingUndo = it.pendingUndo?.takeUnless { pending -> pending.key == key }) }
    }

    private fun updateLoaded(update: (PiSessionsUiState.Loaded) -> PiSessionsUiState.Loaded) {
        val current = _state.value as? PiSessionsUiState.Loaded ?: return
        _state.value = update(current)
    }

    companion object {
        const val UNDO_WINDOW_MS = 3_000L
    }
}

private fun deleteFailureMessage(failure: Throwable): String {
    val error = failure.appError
    return when {
        error is AppError.Http && error.status == 409 -> "A running session can't be deleted."
        else -> error.displayMessage
    }
}
