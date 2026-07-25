package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.ServiceStreamEvent
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.core.net.StreamRequest
import com.hpz.llmdockchat.core.net.parseServiceStreamFrame
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.ServiceSummary
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * The live `GET /api/services/stream` (F07-R1's third criterion, F00-R12):
 * a snapshot on connect, then deltas as containers start or stop, or a
 * favorite flag changes, anywhere — the dashboard, another client, this one.
 *
 * [F10] is expected to reuse this unchanged for the models list — everything
 * here is generic over "the current service list", nothing specific to the
 * model picker.
 */
class ServicesStreamRepository(private val transport: SseTransport) {

    /**
     * Emits the current service list every time it changes. Never completes on
     * its own: a dropped connection (the server restarting, a network blip) is
     * retried after [reconnectDelayMs] rather than surfaced as a flow failure,
     * since the picker has nothing useful to show for "the stream hiccuped" —
     * it just keeps the last list on screen until the reconnect lands.
     */
    fun stream(reconnectDelayMs: Long = RECONNECT_DELAY_MS): Flow<List<ServiceSummary>> = flow {
        var current = emptyList<ServiceSummary>()
        while (true) {
            try {
                transport.open(StreamRequest(path = Endpoints.SERVICES_STREAM))
                    .collect { payload ->
                        current = mergeServiceEvent(current, parseServiceStreamFrame(payload))
                        emit(current)
                    }
            } catch (e: CancellationException) {
                // The collector went away (the sheet closed, a downstream
                // `take`/screen navigation) — not a dropped connection. Must
                // propagate, never be treated as "reconnect": swallowing it
                // here would keep this loop alive after its own job is
                // already cancelled, spinning on `delay` forever.
                throw e
            } catch (e: Throwable) {
                // A dropped connection — retried below rather than surfaced,
                // since the picker has nothing better to show than the last
                // list it had.
            }
            delay(reconnectDelayMs)
        }
    }

    /**
     * Same reconnecting loop as [stream], but surfaces connection health
     * alongside the list (F10-R1's fifth criterion): [ServicesStreamState.stale]
     * flips true the moment a connection attempt fails, so the Models tab can
     * show "reconnecting" instead of going quiet, and flips back to false as
     * soon as the retry lands — which, since `services_stream` always opens
     * with a fresh snapshot, *is* the "falls back to a snapshot fetch" the
     * requirement asks for; a second, separate REST call would read the same
     * `get_docker_services()` data over again for no benefit.
     *
     * Additive on purpose — [stream] is untouched, so F03/F07/F09's callers
     * see no behaviour change.
     */
    fun streamWithStatus(reconnectDelayMs: Long = RECONNECT_DELAY_MS): Flow<ServicesStreamState> = flow {
        var current = emptyList<ServiceSummary>()
        while (true) {
            try {
                transport.open(StreamRequest(path = Endpoints.SERVICES_STREAM))
                    .collect { payload ->
                        current = mergeServiceEvent(current, parseServiceStreamFrame(payload))
                        emit(ServicesStreamState(current, stale = false))
                    }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Throwable) {
                emit(ServicesStreamState(current, stale = true))
            }
            delay(reconnectDelayMs)
        }
    }

    companion object {
        const val RECONNECT_DELAY_MS = 2_000L
    }
}

/** [services] is the last list known, [stale] true while a dropped connection is being retried. */
data class ServicesStreamState(val services: List<ServiceSummary>, val stale: Boolean)

/**
 * Pure and separately tested. A [ServiceStreamEvent.Snapshot] replaces
 * [current] wholesale; a [ServiceStreamEvent.Delta] updates the one named
 * service in place, leaving every other row untouched; [ServiceStreamEvent.Error]
 * and [ServiceStreamEvent.Unknown] leave [current] as it was — an unrecognised
 * frame is exactly the case a live picker must not go blank over.
 */
fun mergeServiceEvent(current: List<ServiceSummary>, event: ServiceStreamEvent): List<ServiceSummary> =
    when (event) {
        is ServiceStreamEvent.Snapshot -> event.services.map { it.toDomain() }
        is ServiceStreamEvent.Delta -> current.map { service ->
            if (service.name != event.serviceName) {
                service
            } else {
                service.copy(
                    status = event.status ?: service.status,
                    favorite = event.favorite ?: service.favorite,
                )
            }
        }
        is ServiceStreamEvent.Error, is ServiceStreamEvent.Unknown -> current
    }
