package com.hpz.llmdockchat.feature.models

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import com.hpz.llmdockchat.data.model.ServiceConfig
import com.hpz.llmdockchat.data.model.ServiceSummary
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

sealed interface ModelDetailUiState {
    data object Loading : ModelDetailUiState

    data class Loaded(
        val summary: ServiceSummary,
        val config: ServiceConfig? = null,
        /** F11-R2's fourth criterion: Docker knows this container but
         * `services.json` doesn't (a 404 on the config fetch). Shown as a
         * graceful partial view, never as [Failed]. */
        val configMissing: Boolean = false,
    ) : ModelDetailUiState

    data class Failed(val message: String) : ModelDetailUiState
}

/**
 * F11-R1's detail screen. [summary] tracks the same live services stream the
 * Models list uses (F11-R1's first two criteria) — [ModelDetailScreen]
 * collects [observeServicesStream] from a composition-scoped `LaunchedEffect`,
 * the same ownership split [ModelsViewModel] uses and for the same reason
 * (F11-R1's third criterion: navigating back and forward must not lose the
 * live connection, which only holds if the stream is re-subscribed by a
 * fresh composition each time, not kept in this ViewModel's own scope across
 * a back-then-forward that recreates it).
 */
class ModelDetailViewModel(
    private val serviceName: String,
    private val servicesRepository: ServicesRepository,
    private val servicesStreamRepository: ServicesStreamRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<ModelDetailUiState>(ModelDetailUiState.Loading)
    val state: StateFlow<ModelDetailUiState> = _state.asStateFlow()

    val controller = ServiceControlController(servicesRepository, viewModelScope)
    val actionState: StateFlow<ServiceActionState> = controller.actionState

    fun requestStart() = controller.requestStart(serviceName)
    fun requestStop() = controller.requestStop(serviceName)
    fun dismissAction() = controller.dismiss()
    fun confirmAction() = controller.confirm()

    private var started = false

    fun start() {
        if (started) return
        started = true
        viewModelScope.launch {
            val services = servicesRepository.list().getOrElse { failure ->
                started = false
                _state.value = ModelDetailUiState.Failed(failure.appError.displayMessage)
                return@launch
            }
            val summary = services.firstOrNull { it.name == serviceName }
            if (summary == null) {
                started = false
                _state.value = ModelDetailUiState.Failed("Service \"$serviceName\" not found.")
                return@launch
            }

            val config = servicesRepository.detail(serviceName).getOrElse {
                // A failed config fetch is not fatal to the screen — F11-R1
                // still needs to show live status even if the read-only
                // config (F11-R2, Should) could not be loaded.
                null
            }
            _state.value = ModelDetailUiState.Loaded(summary = summary, config = config, configMissing = config == null)
        }
    }

    fun retry() {
        started = false
        start()
    }

    /** Collected by [ModelDetailScreen] from a composition-scoped `LaunchedEffect` — see the class doc. */
    fun observeServicesStream(): Flow<ServiceSummary?> =
        servicesStreamRepository.streamWithStatus().map { live -> live.services.firstOrNull { it.name == serviceName } }

    fun applyLiveSummary(summary: ServiceSummary?) {
        if (summary == null) return
        val current = _state.value
        if (current is ModelDetailUiState.Loaded) {
            _state.value = current.copy(summary = summary)
        }
    }
}
