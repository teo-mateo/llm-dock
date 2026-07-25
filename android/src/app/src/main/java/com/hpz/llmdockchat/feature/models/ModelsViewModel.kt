package com.hpz.llmdockchat.feature.models

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.data.GpuStreamRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.ServicesStreamState
import com.hpz.llmdockchat.data.model.GpuState
import com.hpz.llmdockchat.data.model.ServiceSummary
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * F00-R5's Loading/Loaded/Failed. [Loaded] is already split running-above-stopped
 * (F10-R2) — the ordering within each group is whatever [ServiceSummary] arrived
 * in, which is stable because the server sorts by `host_port` and only a row's
 * `status` field changes underneath it, never its position.
 */
sealed interface ModelsUiState {
    data object Loading : ModelsUiState

    data class Loaded(
        val running: List<ServiceSummary>,
        val stopped: List<ServiceSummary>,
        /** True while the services stream is down and being retried (F10-R1's fifth criterion). */
        val stale: Boolean = false,
        val gpu: GpuState = GpuState.Unavailable(null),
    ) : ModelsUiState

    data class Failed(val message: String) : ModelsUiState
}

/** Running first, stopped second — the payload's own `host_port` order preserved within each. */
fun List<ServiceSummary>.splitByRunning(): Pair<List<ServiceSummary>, List<ServiceSummary>> =
    filter { it.isRunning } to filterNot { it.isRunning }

/**
 * F10-R3's third criterion — "closing the tab stops the stream" — turned out
 * not to hold for anything launched from `viewModelScope`: Navigation
 * Compose's tab-switch idiom (`popUpTo(...) { saveState = true }` +
 * `restoreState = true`, the same one [com.hpz.llmdockchat.navigation.AppNavHost]
 * uses for both tabs) keeps this ViewModel's instance — and therefore
 * anything running in its scope — alive while the Chats tab is showing.
 * Confirmed live: switching to Chats left both the services and GPU SSE
 * sockets in `ss -tnp`'s output, still `ESTAB`.
 *
 * So the two live subscriptions are *not* owned by this ViewModel's own
 * scope. [observeServicesStream]/[observeGpuStream] hand back the bare
 * [Flow]s; [ModelsScreen] collects them from a `LaunchedEffect` tied to its
 * own composition, which Navigation Compose disposes the moment this
 * destination stops being current (the same disposal
 * [com.hpz.llmdockchat.feature.conversations.ConversationListScreen] already
 * relies on for its own re-fetch-on-return). [start] keeps only the cheap,
 * one-shot initial REST fetch — that one is fine to leave cached.
 */
class ModelsViewModel(
    private val servicesRepository: ServicesRepository,
    private val servicesStreamRepository: ServicesStreamRepository,
    private val gpuStreamRepository: GpuStreamRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<ModelsUiState>(ModelsUiState.Loading)
    val state: StateFlow<ModelsUiState> = _state.asStateFlow()

    /** One-shot, same guard as [com.hpz.llmdockchat.feature.newchat.NewChatViewModel.load]. */
    private var started = false

    fun start() {
        if (started) return
        started = true
        _state.value = ModelsUiState.Loading
        viewModelScope.launch {
            val services = servicesRepository.list().getOrElse { failure ->
                started = false
                _state.value = ModelsUiState.Failed(failure.appError.displayMessage)
                return@launch
            }
            val (running, stopped) = services.splitByRunning()
            _state.value = ModelsUiState.Loaded(running = running, stopped = stopped)
        }
    }

    fun retry() {
        started = false
        start()
    }

    /** Collected by [ModelsScreen] from a composition-scoped `LaunchedEffect` — see the class doc. */
    fun observeServicesStream(): Flow<ServicesStreamState> = servicesStreamRepository.streamWithStatus()

    /** Collected by [ModelsScreen] from a composition-scoped `LaunchedEffect` — see the class doc. */
    fun observeGpuStream(): Flow<GpuState> = gpuStreamRepository.stream()

    fun applyServicesUpdate(live: ServicesStreamState) {
        val (running, stopped) = live.services.splitByRunning()
        updateLoaded { it.copy(running = running, stopped = stopped, stale = live.stale) }
    }

    fun applyGpuUpdate(gpu: GpuState) = updateLoaded { it.copy(gpu = gpu) }

    private inline fun updateLoaded(transform: (ModelsUiState.Loaded) -> ModelsUiState.Loaded) {
        val current = _state.value
        if (current is ModelsUiState.Loaded) _state.value = transform(current)
    }
}
