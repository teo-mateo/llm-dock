package com.hpz.llmdockchat.feature.pi

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.data.PiCommandsRepository
import com.hpz.llmdockchat.data.model.PiCommandOutcome
import com.hpz.llmdockchat.data.model.PiSessionKey
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class PiComposerState(
    val draft: String = "",
    val sending: Boolean = false,
    val stopping: Boolean = false,
    val notice: String? = null,
    val lastStopAt: Long? = null,
)

internal class PiSessionViewModel(
    private val key: PiSessionKey,
    private val runtime: PiSessionRuntime,
    private val commandsRepository: PiCommandsRepository,
    private val clock: () -> Long = System::currentTimeMillis,
) : ViewModel() {
    val state = runtime.state
    private val _composerState = MutableStateFlow(PiComposerState())
    val composerState: StateFlow<PiComposerState> = _composerState.asStateFlow()

    fun start() = runtime.start(viewModelScope)
    fun flush() = runtime.flush()

    override fun onCleared() {
        runtime.stop()
        super.onCleared()
    }

    fun onDraftChange(value: String) {
        _composerState.value = _composerState.value.copy(draft = value)
    }

    fun send() {
        val server = runtime.commandServer() ?: return
        val current = _composerState.value
        if (current.draft.isBlank() || current.sending) return
        _composerState.value = current.copy(sending = true)
        viewModelScope.launch {
            try {
                val outcome = commandsRepository.send(key, current.draft, server)
                if (runtime.commandServer() != server) return@launch
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
                )
            } finally {
                _composerState.value = _composerState.value.copy(sending = false)
            }
        }
    }

    fun stop() {
        val server = runtime.commandServer() ?: return
        val current = _composerState.value
        if (current.stopping) return
        _composerState.value = current.copy(stopping = true, lastStopAt = clock())
        viewModelScope.launch {
            try {
                commandsRepository.abort(key, server)
            } finally {
                _composerState.value = _composerState.value.copy(stopping = false)
            }
        }
    }
}
