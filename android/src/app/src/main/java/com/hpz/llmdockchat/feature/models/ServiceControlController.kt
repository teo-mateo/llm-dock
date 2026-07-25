package com.hpz.llmdockchat.feature.models

import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.data.ServicesRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class ServiceAction { START, STOP }

/**
 * One confirm-then-act flow, shared by [ModelsViewModel]'s row actions
 * (F10-R5) and the detail screen's (F11-R3/R4) — both must "go through the
 * same confirmation path", which is easiest to guarantee by them sharing the
 * same class rather than two hand-written copies drifting apart.
 */
sealed interface ServiceActionState {
    data object Idle : ServiceActionState
    data class Confirming(val serviceName: String, val action: ServiceAction) : ServiceActionState
    data class InFlight(val serviceName: String, val action: ServiceAction) : ServiceActionState

    /** A failed start/stop — F11-R3's "leaves the status as it actually is" and
     * F11-R4's "shows the server's error": neither pretends success. */
    data class Failed(val serviceName: String, val action: ServiceAction, val message: String) : ServiceActionState
}

/**
 * [scope] is the caller's `viewModelScope` — unlike the SSE streams, a
 * start/stop POST is a one-shot call and is fine to let ride out a
 * navigation away exactly like any other in-flight request in this codebase
 * (e.g. [com.hpz.llmdockchat.feature.thread.ThreadViewModel]'s send).
 */
class ServiceControlController(
    private val servicesRepository: ServicesRepository,
    private val scope: CoroutineScope,
) {
    private val _actionState = MutableStateFlow<ServiceActionState>(ServiceActionState.Idle)
    val actionState: StateFlow<ServiceActionState> = _actionState.asStateFlow()

    /** Opens the confirm dialog. A no-op while something is already in flight —
     * F11-R4's third criterion, "cannot be double-fired" — a second tap on a
     * different row while one is running is refused the same way. */
    fun requestStart(serviceName: String) = requestConfirm(serviceName, ServiceAction.START)

    fun requestStop(serviceName: String) = requestConfirm(serviceName, ServiceAction.STOP)

    private fun requestConfirm(serviceName: String, action: ServiceAction) {
        if (_actionState.value is ServiceActionState.InFlight) return
        _actionState.value = ServiceActionState.Confirming(serviceName, action)
    }

    /** Back out of the confirm dialog, or dismiss a failure, without acting. */
    fun dismiss() {
        if (_actionState.value is ServiceActionState.InFlight) return
        _actionState.value = ServiceActionState.Idle
    }

    /** The confirm button. Only fires the request from [ServiceActionState.Confirming] —
     * called from any other state (already in flight, already idle) it does nothing. */
    fun confirm() {
        val pending = _actionState.value as? ServiceActionState.Confirming ?: return
        _actionState.value = ServiceActionState.InFlight(pending.serviceName, pending.action)
        scope.launch {
            val result = when (pending.action) {
                ServiceAction.START -> servicesRepository.start(pending.serviceName)
                ServiceAction.STOP -> servicesRepository.stop(pending.serviceName)
            }
            _actionState.value = result.fold(
                onSuccess = { ServiceActionState.Idle },
                onFailure = { ServiceActionState.Failed(pending.serviceName, pending.action, it.appError.displayMessage) },
            )
        }
    }

    /** Whether [serviceName] specifically is mid-request — what a row/button
     * checks to show its own pending state (F10-R5's third criterion). */
    fun isInFlight(serviceName: String): Boolean =
        (_actionState.value as? ServiceActionState.InFlight)?.serviceName == serviceName
}
