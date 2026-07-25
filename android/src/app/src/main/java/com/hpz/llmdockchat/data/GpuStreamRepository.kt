package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.GpuStreamEvent
import com.hpz.llmdockchat.core.net.ReconnectBackoff
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.core.net.StreamRequest
import com.hpz.llmdockchat.core.net.parseGpuStreamFrame
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.GpuState
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * The live `GET /api/gpu/stream` (F10-R3): one frame per tick, no snapshot/delta
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
     * Emits [GpuState.Unavailable] immediately on connect (F10-R3's fourth
     * criterion: a header that has not heard from the server yet must not look
     * "available" with stale zeros), then whatever the stream reports. Never
     * completes on its own — a dropped connection is retried, not surfaced as
     * a flow failure, same posture as [ServicesStreamRepository.stream].
     */
    fun stream(interval: Double = DEFAULT_INTERVAL_S, backoff: ReconnectBackoff = ReconnectBackoff()): Flow<GpuState> = flow {
        emit(GpuState.Unavailable(null))
        while (true) {
            try {
                transport.open(
                    StreamRequest(path = Endpoints.GPU_STREAM, query = mapOf("interval" to interval.toString())),
                ).collect { payload ->
                    when (val event = parseGpuStreamFrame(payload)) {
                        is GpuStreamEvent.Frame -> {
                            backoff.reset()
                            val gpus = event.gpus.map { it.toDomain() }
                            emit(if (gpus.isEmpty()) GpuState.Unavailable(null) else GpuState.Available(gpus))
                        }
                        is GpuStreamEvent.Error -> emit(GpuState.Unavailable(event.message))
                        // An unrecognised frame is left alone rather than blanking
                        // the header over a payload shape this client doesn't know yet.
                        is GpuStreamEvent.Unknown -> Unit
                    }
                }
            } catch (e: CancellationException) {
                // The screen went away — propagate, never treated as "reconnect"
                // (same reasoning as ServicesStreamRepository.stream).
                throw e
            } catch (e: Throwable) {
                emit(GpuState.Unavailable(null))
            }
            delay(backoff.next())
        }
    }

    companion object {
        const val DEFAULT_INTERVAL_S = 3.0
    }
}
