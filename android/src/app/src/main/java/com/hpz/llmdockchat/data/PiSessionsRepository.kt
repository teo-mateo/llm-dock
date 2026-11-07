package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.ServerUrlStore
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.PiSessionsStreamEvent
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.core.net.StreamRequest
import com.hpz.llmdockchat.core.net.parsePiSessionsStreamFrame
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

data class PiSessionsState(
    val sessions: List<PiSession>,
    val stale: Boolean,
)

private class LaggedStreamSignal : RuntimeException()

class PiSessionsRepository(
    private val transport: SseTransport,
    private val serverUrlStore: ServerUrlStore? = null,
    private val onRemoved: (BaseUrl, PiSessionKey) -> Unit = { _, _ -> },
) {

    fun streamWithStatus(reconnectDelayMs: Long = RECONNECT_DELAY_MS): Flow<PiSessionsState> = flow {
        val server = serverUrlStore?.current()
        var current = emptyList<PiSession>()
        while (true) {
            var lagged = false
            try {
                transport.open(StreamRequest(path = Endpoints.PI_SESSIONS_STREAM, expectedServer = server))
                    .collect { payload ->
                        val event = parsePiSessionsStreamFrame(payload)
                        if (event is PiSessionsStreamEvent.Removed && server != null) {
                            onRemoved(server, PiSessionKey(event.sessionId, event.instanceId))
                        }
                        if (event is PiSessionsStreamEvent.Lagged) {
                            lagged = true
                            throw LaggedStreamSignal()
                        }
                        current = sortPiSessions(mergePiSessionsEvent(current, event))
                        emit(PiSessionsState(current, stale = false))
                    }
            } catch (e: CancellationException) {
                throw e
            } catch (e: LaggedStreamSignal) {
            } catch (e: Throwable) {
                emit(PiSessionsState(current, stale = true))
            }
            if (!lagged) delay(reconnectDelayMs)
        }
    }

    companion object {
        const val RECONNECT_DELAY_MS = 3_000L
    }
}

fun mergePiSessionsEvent(
    current: List<PiSession>,
    event: PiSessionsStreamEvent,
): List<PiSession> = when (event) {
    is PiSessionsStreamEvent.Snapshot -> event.sessions.map { it.toDomain() }
    is PiSessionsStreamEvent.Session -> {
        val session = event.session.toDomain()
        if (current.any { it.key == session.key }) {
            current.map { if (it.key == session.key) session else it }
        } else {
            current + session
        }
    }
    is PiSessionsStreamEvent.Removed ->
        current.filterNot { it.key.sessionId == event.sessionId && it.key.instanceId == event.instanceId }
    is PiSessionsStreamEvent.Lagged, is PiSessionsStreamEvent.Unknown -> current
}

fun sortPiSessions(list: List<PiSession>): List<PiSession> =
    list.sortedWith(compareByDescending<PiSession> { it.live }.thenByDescending { it.lastSeen })
