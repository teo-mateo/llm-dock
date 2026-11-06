package com.hpz.llmdockchat.feature.pi

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.data.PiCommandsRepository
import com.hpz.llmdockchat.data.PiSessionEventsRepository
import com.hpz.llmdockchat.data.model.PiCommandOutcome
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

data class PiComposerState(
    val draft: String = "",
    val sending: Boolean = false,
    val stopping: Boolean = false,
    val notice: String? = null,
    val lastStopAt: Long? = null,
)

class PiSessionViewModel(
    private val key: PiSessionKey,
    private val repository: PiSessionEventsRepository,
    private val commandsRepository: PiCommandsRepository,
    private val clock: () -> Long = System::currentTimeMillis,
) : ViewModel() {
    private val _state = MutableStateFlow<PiSessionUiState>(PiSessionUiState.Loading)
    val state: StateFlow<PiSessionUiState> = _state.asStateFlow()
    private val _composerState = MutableStateFlow(PiComposerState())
    val composerState: StateFlow<PiComposerState> = _composerState.asStateFlow()
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

    fun onDraftChange(value: String) {
        _composerState.value = _composerState.value.copy(draft = value)
    }

    fun send() {
        val current = _composerState.value
        if (current.draft.isBlank() || current.sending) return
        _composerState.value = current.copy(sending = true)
        viewModelScope.launch {
            val outcome = commandsRepository.send(key, current.draft)
            val message = outcomeMessage(outcome)
            _composerState.value = _composerState.value.copy(
                draft = if (outcome == PiCommandOutcome.Done || outcome == PiCommandOutcome.Pending) {
                    ""
                } else {
                    _composerState.value.draft
                },
                notice = if (outcome == PiCommandOutcome.Done || outcome == PiCommandOutcome.Pending) {
                    null
                } else {
                    message
                },
                sending = false,
            )
        }
    }

    fun stop() {
        val current = _composerState.value
        if (current.stopping) return
        _composerState.value = current.copy(stopping = true, lastStopAt = clock())
        viewModelScope.launch {
            try {
                commandsRepository.abort(key)
            } finally {
                _composerState.value = _composerState.value.copy(stopping = false)
            }
        }
    }
}
