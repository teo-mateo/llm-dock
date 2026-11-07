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
    val appended: List<PiEvent>,
    val lastSeq: Long,
    val summary: PiSession?,
    val stale: Boolean,
    val unknown: Boolean,
)

private class LaggedSessionEventsSignal : RuntimeException()
private class RemovedSessionEventsSignal : RuntimeException()

class PiSessionEventsRepository(private val transport: SseTransport) {

    fun stream(
        key: PiSessionKey,
        reconnectDelayMs: Long = RECONNECT_DELAY_MS,
        after: Long = 0L,
    ): Flow<PiSessionEventsState> = flow {
        require(after >= 0L) { "Resume cursor must be non-negative" }
        var summary: PiSession? = null
        var lastSeq = after
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
                            val appended = freshPiSessionEvents(
                                lastSeq,
                                event.events.map { PiEvent(it.seq, it.type, it.ts, it.payload) },
                            )
                            lastSeq = appended.lastOrNull()?.seq ?: lastSeq
                            emit(PiSessionEventsState(appended, lastSeq, summary, stale = false, unknown = false))
                        }
                        is PiSessionStreamEvent.Session -> {
                            summary = event.session.toDomain()
                            emit(PiSessionEventsState(emptyList(), lastSeq, summary, stale = false, unknown = false))
                        }
                        is PiSessionStreamEvent.Lagged -> {
                            lagged = true
                            throw LaggedSessionEventsSignal()
                        }
                        is PiSessionStreamEvent.Removed -> {
                            if (event.sessionId == key.sessionId && event.instanceId == key.instanceId) {
                                throw RemovedSessionEventsSignal()
                            }
                        }
                        is PiSessionStreamEvent.Unknown -> Unit
                    }
                }
                emit(PiSessionEventsState(emptyList(), lastSeq, summary, stale = true, unknown = false))
            } catch (e: CancellationException) {
                throw e
            } catch (e: LaggedSessionEventsSignal) {
            } catch (e: RemovedSessionEventsSignal) {
                emit(PiSessionEventsState(emptyList(), lastSeq, summary, stale = false, unknown = true))
                return@flow
            } catch (e: Throwable) {
                val error = e.appError
                if (error is AppError.Http && error.status == 404) {
                    emit(PiSessionEventsState(emptyList(), lastSeq, summary, stale = false, unknown = true))
                    return@flow
                }
                emit(PiSessionEventsState(emptyList(), lastSeq, summary, stale = true, unknown = false))
            }
            if (!lagged) delay(reconnectDelayMs)
        }
    }

    companion object {
        const val RECONNECT_DELAY_MS = 3_000L
    }
}

fun freshPiSessionEvents(after: Long, incoming: List<PiEvent>): List<PiEvent> = incoming
    .filter { it.seq > after }
    .sortedBy { it.seq }
    .distinctBy { it.seq }
