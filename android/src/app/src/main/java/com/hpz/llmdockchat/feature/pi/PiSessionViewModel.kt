package com.hpz.llmdockchat.feature.pi

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.data.PiSessionEventsRepository
import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.feature.pi.transcript.PiTranscript
import com.hpz.llmdockchat.feature.pi.transcript.buildPiTranscript
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

sealed interface PiSessionUiState {
    data object Loading : PiSessionUiState
    data object Unknown : PiSessionUiState
    data class Loaded(
        val summary: PiSession?,
        val transcript: PiTranscript,
        val stale: Boolean,
    ) : PiSessionUiState
}

class PiSessionViewModel(
    private val key: PiSessionKey,
    private val repository: PiSessionEventsRepository,
) : ViewModel() {
    private val _state = MutableStateFlow<PiSessionUiState>(PiSessionUiState.Loading)
    val state: StateFlow<PiSessionUiState> = _state.asStateFlow()
    private var started = false

    fun start() {
        if (started) return
        started = true
        viewModelScope.launch {
            repository.stream(key).collect { update ->
                if (update.unknown) {
                    _state.value = PiSessionUiState.Unknown
                } else {
                    val transcript = withContext(Dispatchers.Default) {
                        buildPiTranscript(update.events)
                    }
                    _state.value = PiSessionUiState.Loaded(
                        summary = update.summary,
                        transcript = transcript,
                        stale = update.stale,
                    )
                }
            }
        }
    }
}
