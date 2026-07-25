package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.LogStreamEvent
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.core.net.StreamRequest
import com.hpz.llmdockchat.core.net.parseLogStreamFrame
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

/**
 * The live `GET /api/services/<name>/logs/stream` (F12-R1).
 *
 * Deliberately unlike [GpuStreamRepository] and [ServicesStreamRepository]:
 * this does **not** loop and reconnect on its own. A container's log stream
 * ending (`stream_end`) is a normal outcome — the container was stopped — and
 * reconnecting into it would just open the same finished stream again. A
 * genuine connection drop instead completes the flow with an exception, which
 * [com.hpz.llmdockchat.feature.logs.LogsViewModel] turns into a visible error
 * rather than silently retrying, so the screen's "live"/"ended" state always
 * reflects what actually happened.
 */
class LogsStreamRepository(private val transport: SseTransport) {

    fun stream(serviceName: String, tail: Int = DEFAULT_TAIL): Flow<LogStreamEvent> =
        transport.open(
            StreamRequest(path = Endpoints.serviceLogsStream(serviceName), query = mapOf("tail" to tail.toString())),
        ).map { parseLogStreamFrame(it) }

    companion object {
        const val DEFAULT_TAIL = 200
    }
}
