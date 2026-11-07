package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.BaseUrl
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
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.flow

data class PiSessionEventsState(
    val appended: List<PiEvent>,
    val lastSeq: Long,
    val summary: PiSession?,
    val stale: Boolean,
    val unknown: Boolean,
    val caughtUp: Boolean = false,
)

private class LaggedSessionEventsSignal : RuntimeException()
private class RemovedSessionEventsSignal : RuntimeException()

class PiSessionEventsRepository(private val transport: SseTransport) {
    fun stream(
        key: PiSessionKey,
        reconnectDelayMs: Long = RECONNECT_DELAY_MS,
        after: Long = 0L,
        expectedServer: BaseUrl? = null,
    ): Flow<PiSessionEventsState> = flow {
        require(after >= 0L) { "Resume cursor must be non-negative" }
        var summary: PiSession? = null
        var lastSeq = after
        while (true) {
            var lagged = false
            var caughtUp = false
            val request = StreamRequest(
                path = Endpoints.piSessionStream(key.sessionId, key.instanceId),
                query = mapOf("after" to lastSeq.toString()),
                expectedServer = expectedServer,
            )
            try {
                flow<Result<String>> {
                    transport.open(request).collect { emit(Result.success(it)) }
                }.catch { error ->
                    if (error is CancellationException || error.appError == AppError.Unauthenticated) throw error
                    emit(Result.failure(error))
                }.collect { frame ->
                    if (frame.isFailure) {
                        if ((frame.exceptionOrNull()?.appError as? AppError.Http)?.status == 404) {
                            throw RemovedSessionEventsSignal()
                        }
                        return@collect
                    }
                    when (val event = parsePiSessionStreamFrame(frame.getOrThrow())) {
                        is PiSessionStreamEvent.Events -> {
                            val appended = freshPiSessionEvents(lastSeq, event.events.map { PiEvent(it.seq, it.type, it.ts, it.payload) })
                            lastSeq = appended.lastOrNull()?.seq ?: lastSeq
                            emit(PiSessionEventsState(appended, lastSeq, summary, false, false, caughtUp))
                        }
                        is PiSessionStreamEvent.Session -> {
                            summary = event.session.toDomain()
                            caughtUp = true
                            emit(PiSessionEventsState(emptyList(), lastSeq, summary, false, false, true))
                        }
                        is PiSessionStreamEvent.Lagged -> {
                            lagged = true
                            emit(PiSessionEventsState(emptyList(), lastSeq, summary, false, false))
                            throw LaggedSessionEventsSignal()
                        }
                        is PiSessionStreamEvent.Removed -> {
                            if (event.sessionId == key.sessionId && event.instanceId == key.instanceId) throw RemovedSessionEventsSignal()
                        }
                        is PiSessionStreamEvent.Unknown -> Unit
                    }
                }
                emit(PiSessionEventsState(emptyList(), lastSeq, summary, true, false))
            } catch (_: LaggedSessionEventsSignal) {
            } catch (_: RemovedSessionEventsSignal) {
                emit(PiSessionEventsState(emptyList(), lastSeq, summary, false, true))
                return@flow
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
