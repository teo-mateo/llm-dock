package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.net.isTransient
import com.hpz.llmdockchat.core.net.GpuStreamEvent
import com.hpz.llmdockchat.core.net.ReconnectBackoff
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.core.net.StreamRequest
import com.hpz.llmdockchat.core.net.parseGpuStreamFrame
import com.hpz.llmdockchat.core.error.displayMessage
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.GpuState
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * The live `GET /api/gpu/stream`: one frame per tick, no snapshot/delta
 * split — every frame is the full, current GPU list, so there is nothing to
 * merge (unlike [ServicesStreamRepository]).
 *
 * Reconnects with [ReconnectBackoff] rather than a flat delay, deliberately
 * unlike [ServicesStreamRepository.RECONNECT_DELAY_MS]: the Models tab can sit
 * open for as long as the screen is, the same reasoning
 * [com.hpz.llmdockchat.core.net.ReconnectBackoff] itself gives for a thread's
 * chat stream.
 */
class GpuStreamRepository(private val transport: SseTransport) {

    /**
     * Emits [GpuState.Connecting] immediately on connect: a header that has not heard from the server yet must not look
     * "available" with stale zeros — nor claim the GPU is unavailable, which
     * is a different statement), then whatever the stream reports. Never
     * completes on its own — a dropped connection is retried, not surfaced as
     * a flow failure, same posture as [ServicesStreamRepository.stream].
     */
    fun stream(
        interval: Double = DEFAULT_INTERVAL_S,
        backoff: ReconnectBackoff = ReconnectBackoff(),
        terminalBackoff: ReconnectBackoff = ReconnectBackoff(
            initialMs = ReconnectBackoff.DEFAULT_INITIAL_MS,
            maxMs = TERMINAL_MAX_MS,
        ),
    ): Flow<GpuState> = flow {
        emit(GpuState.Connecting)
        while (true) {
            var waitMs: Long
            try {
                transport.open(
                    StreamRequest(path = Endpoints.GPU_STREAM, query = mapOf("interval" to interval.toString())),
                ).collect { payload ->
                    when (val event = parseGpuStreamFrame(payload)) {
                        is GpuStreamEvent.Frame -> {
                            backoff.reset()
                            terminalBackoff.reset()
                            val gpus = event.gpus.map { it.toDomain() }
                            emit(if (gpus.isEmpty()) GpuState.Unavailable(null) else GpuState.Available(gpus))
                        }
                        is GpuStreamEvent.Error -> emit(GpuState.Unavailable(event.message))
                        // An unrecognised frame is left alone rather than blanking
                        // the header over a payload shape this client doesn't know yet.
                        is GpuStreamEvent.Unknown -> Unit
                    }
                }
                waitMs = backoff.next()
            } catch (e: CancellationException) {
                // The screen went away — propagate, never treated as "reconnect"
                // (same reasoning as ServicesStreamRepository.stream).
                throw e
            } catch (e: Throwable) {
                val error = e.appError
                if (error.isTransient()) {
                    emit(GpuState.Unavailable(error.displayMessage))
                    waitMs = terminalBackoff.next()
                } else {
                    // A 401 re-auth could not fix, or a 404, answers the same
                    // way however often it is asked — but the dashboard can be
                    // restarted under a client that is still on the screen, so
                    // the stream keeps trying, slowly, and says why meanwhile.
                    emit(GpuState.Unavailable(error.displayMessage))
                    waitMs = terminalBackoff.next()
                }
            }
            delay(waitMs)
        }
    }

    companion object {
        const val DEFAULT_INTERVAL_S = 3.0

        /** A terminal failure is retried, but at a pace that costs nothing to leave running. */
        const val TERMINAL_MAX_MS = 60_000L
    }
}
