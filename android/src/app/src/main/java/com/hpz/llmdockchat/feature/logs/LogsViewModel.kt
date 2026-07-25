package com.hpz.llmdockchat.feature.logs

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.LogStreamEvent
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.data.LogsStreamRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.model.LogLevel
import com.hpz.llmdockchat.data.model.classifyLogLevel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** One rendered row. [level] degrades to [LogLevel.PLAIN] for anything F12-R4 doesn't recognise. */
data class LogLine(val text: String, val level: LogLevel)

/** How the on-screen buffer was populated, and whether it is still live. */
enum class LogsConnection {
    /** The stream is open; the historical tail may still be arriving. */
    CONNECTING,

    /** The stream is open and the tail has been delivered — new lines are live output. */
    LIVE,

    /** The container's log stream ended normally (`stream_end`) — not a failure. */
    ENDED,

    /** The stream could not be established; [LogsUiState.Loaded.lines] came from the one-shot fallback (F12-R3). */
    FALLBACK,
}

sealed interface LogsUiState {
    data object Loading : LogsUiState

    /** 404 — the service exists in `services.json` but has no container yet. */
    data class NotCreated(val message: String) : LogsUiState

    /** Neither the stream nor the one-shot fallback could produce anything. */
    data class Failed(val message: String) : LogsUiState

    data class Loaded(
        val lines: List<LogLine>,
        /** Index into [lines] where the historical tail ended — null until `snapshot_end` (or never, for [LogsConnection.FALLBACK]). */
        val boundaryIndex: Int?,
        val connection: LogsConnection,
    ) : LogsUiState
}

/**
 * F12-R1/R2/R3/R4. [observeLogStream] is collected by [LogsScreen] from a
 * composition-scoped `LaunchedEffect`, not from [viewModelScope] — the same
 * split [ModelDetailViewModel] uses, and for the same reason: F10 shipped a
 * bug where a stream launched in `viewModelScope` outlived the screen because
 * Navigation Compose keeps the ViewModel alive across a tab switch. Collecting
 * in the screen's own composition means leaving it cancels the flow, which
 * cancels the underlying OkHttp call (F12-R1's last criterion).
 */
class LogsViewModel(
    private val serviceName: String,
    private val logsStreamRepository: LogsStreamRepository,
    private val servicesRepository: ServicesRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<LogsUiState>(LogsUiState.Loading)
    val state: StateFlow<LogsUiState> = _state.asStateFlow()

    private val lines = mutableListOf<LogLine>()
    private var boundaryIndex: Int? = null
    private var sawAnyFrame = false

    /** Collected by [LogsScreen] — see the class doc. Never started from here. */
    fun observeLogStream(): Flow<LogStreamEvent> = logsStreamRepository.stream(serviceName)

    fun onStreamEvent(event: LogStreamEvent) {
        sawAnyFrame = true
        when (event) {
            is LogStreamEvent.SnapshotStart -> publish(LogsConnection.CONNECTING)
            is LogStreamEvent.Log -> {
                lines += LogLine(event.line, classifyLogLevel(event.line))
                publish(LogsConnection.CONNECTING)
            }
            is LogStreamEvent.SnapshotEnd -> {
                boundaryIndex = lines.size
                publish(LogsConnection.LIVE)
            }
            is LogStreamEvent.StreamEnd -> publish(LogsConnection.ENDED)
            is LogStreamEvent.Error -> _state.value = LogsUiState.Failed(event.message)
            is LogStreamEvent.Unknown -> Unit
        }
    }

    /** The flow completed without an explicit `stream_end` — treated the same: an end state, not a failure. */
    fun onStreamCompleted() {
        if (sawAnyFrame) publish(LogsConnection.ENDED)
    }

    /**
     * The stream could not be established at all. A 404 means the service has
     * no container yet (F12-R1's fifth criterion) — shown as [LogsUiState.NotCreated],
     * never an empty screen. Anything else falls back to the one-shot fetch
     * (F12-R3); if that fails too, the failure is shown as-is.
     */
    fun onStreamFailed(error: Throwable) {
        if (sawAnyFrame) {
            // A drop mid-stream, not a failure to connect — the buffer already on
            // screen stays, but it's no longer live.
            _state.value = LogsUiState.Failed(error.appError.displayMessage)
            return
        }
        val appError = error.appError
        if (appError is AppError.Http && appError.status == 404) {
            _state.value = LogsUiState.NotCreated(appError.message)
            return
        }
        fetchOnce()
    }

    private fun fetchOnce() {
        viewModelScope.launch {
            servicesRepository.fetchLogsOnce(serviceName).fold(
                onSuccess = { fetched ->
                    lines.clear()
                    lines += fetched.map { LogLine(it, classifyLogLevel(it)) }
                    boundaryIndex = null
                    publish(LogsConnection.FALLBACK)
                },
                onFailure = { failure ->
                    val appError = failure.appError
                    _state.value = if (appError is AppError.Http && appError.status == 404) {
                        LogsUiState.NotCreated(appError.message)
                    } else {
                        LogsUiState.Failed(appError.displayMessage)
                    }
                },
            )
        }
    }

    private fun publish(connection: LogsConnection) {
        _state.value = LogsUiState.Loaded(lines.toList(), boundaryIndex, connection)
    }
}
