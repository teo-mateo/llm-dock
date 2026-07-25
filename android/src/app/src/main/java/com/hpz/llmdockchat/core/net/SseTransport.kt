package com.hpz.llmdockchat.core.net

import kotlinx.coroutines.flow.Flow

data class StreamRequest(
    val path: String,
    val method: String = "GET",
    val query: Map<String, String> = emptyMap(),
    val body: String? = null,
)

/**
 * The only part of streaming that touches the network (Architecture D2).
 *
 * Emits raw `data:` payloads in order. The flow **completes** when the server
 * closes the stream — with or without a terminal frame — and **fails** with an
 * [ApiException] when the connection or the request does. Callers that want to
 * reconnect distinguish the two through `onCompletion`/`catch`.
 */
interface SseTransport {
    fun open(request: StreamRequest): Flow<String>
}
