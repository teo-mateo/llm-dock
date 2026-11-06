package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.PiSessionStreamEvent
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.core.net.StreamRequest
import com.hpz.llmdockchat.core.net.appError
import com.hpz.llmdockchat.core.net.parsePiSessionStreamFrame
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.PiEvent
import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

data class PiSessionEventsState(
    val events: List<PiEvent>,
    val summary: PiSession?,
    val stale: Boolean,
    val unknown: Boolean,
)

private class LaggedSessionEventsSignal(val after: Long) : RuntimeException()

class PiSessionEventsRepository(private val transport: SseTransport) {

    fun stream(
        key: PiSessionKey,
        reconnectDelayMs: Long = RECONNECT_DELAY_MS,
    ): Flow<PiSessionEventsState> = flow {
        var events = emptyList<PiEvent>()
        var summary: PiSession? = null
        var lastSeq = 0L
        while (true) {
            var lagged = false
            try {
                transport.open(
                    StreamRequest(
                        path = Endpoints.piSessionStream(key.sessionId, key.instanceId),
                        query = mapOf("after" to lastSeq.toString()),
                    ),
                ).collect { payload ->
                    when (val event = parsePiSessionStreamFrame(payload)) {
                        is PiSessionStreamEvent.Events -> {
                            events = mergePiSessionEvents(events, event.events.map { PiEvent(it.seq, it.type, it.ts, it.payload) })
                            lastSeq = events.lastOrNull()?.seq ?: lastSeq
                            emit(PiSessionEventsState(events, summary, stale = false, unknown = false))
                        }
                        is PiSessionStreamEvent.Session -> {
                            summary = event.session.toDomain()
                            emit(PiSessionEventsState(events, summary, stale = false, unknown = false))
                        }
                        is PiSessionStreamEvent.Lagged -> {
                            lastSeq = maxOf(lastSeq, event.after)
                            lagged = true
                            throw LaggedSessionEventsSignal(event.after)
                        }
                        is PiSessionStreamEvent.Unknown -> Unit
                    }
                }
                emit(PiSessionEventsState(events, summary, stale = true, unknown = false))
            } catch (e: CancellationException) {
                throw e
            } catch (e: LaggedSessionEventsSignal) {
            } catch (e: Throwable) {
                val error = e.appError
                if (error is AppError.Http && error.status == 404) {
                    emit(PiSessionEventsState(events, summary, stale = false, unknown = true))
                    return@flow
                }
                emit(PiSessionEventsState(events, summary, stale = true, unknown = false))
            }
            if (!lagged) delay(reconnectDelayMs)
        }
    }

    companion object {
        const val RECONNECT_DELAY_MS = 3_000L
    }
}

fun mergePiSessionEvents(current: List<PiEvent>, incoming: List<PiEvent>): List<PiEvent> {
    val lastSeq = current.lastOrNull()?.seq ?: Long.MIN_VALUE
    val fresh = incoming
        .filter { it.seq > lastSeq }
        .sortedBy { it.seq }
        .distinctBy { it.seq }
    return current + fresh
}
