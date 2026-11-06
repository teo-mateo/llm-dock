package com.hpz.llmdockchat.feature.pi

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.data.PiSessionsRepository
import com.hpz.llmdockchat.data.model.PiSession
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface PiSessionsUiState {
    data object Loading : PiSessionsUiState
    data class Loaded(
        val live: List<PiSession>,
        val ended: List<PiSession>,
        val stale: Boolean,
    ) : PiSessionsUiState
}

fun List<PiSession>.splitByLive(): Pair<List<PiSession>, List<PiSession>> =
    filter { it.live } to filterNot { it.live }

class PiSessionsViewModel(private val repository: PiSessionsRepository) : ViewModel() {
    private val _state = MutableStateFlow<PiSessionsUiState>(PiSessionsUiState.Loading)
    val state: StateFlow<PiSessionsUiState> = _state.asStateFlow()
    private var started = false

    fun start() {
        if (started) return
        started = true
        viewModelScope.launch {
            repository.streamWithStatus().collect { update ->
                val (live, ended) = update.sessions.splitByLive()
                _state.value = PiSessionsUiState.Loaded(live = live, ended = ended, stale = update.stale)
            }
        }
    }
}
