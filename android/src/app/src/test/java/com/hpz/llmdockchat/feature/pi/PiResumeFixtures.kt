package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.core.net.StreamRequest
import com.hpz.llmdockchat.data.model.PiEvent
import com.hpz.llmdockchat.feature.pi.transcript.PiSessionSnapshot
import com.hpz.llmdockchat.feature.pi.transcript.TranscriptBuilder
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.flow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject

internal class DrivenPiTransport : SseTransport {
    val frames = Channel<Result<String>>(Channel.UNLIMITED)
    val requests = mutableListOf<StreamRequest>()
    var opening: (StreamRequest) -> Unit = {}
    override fun open(request: StreamRequest) = flow {
        requests += request
        opening(request)
        for (frame in frames) emit(frame.getOrThrow())
    }
    fun send(payload: String) { check(frames.trySend(Result.success(payload)).isSuccess) }
    fun fail(error: Throwable) { check(frames.trySend(Result.failure(error)).isSuccess) }
}

internal fun piEvent(seq: Long, type: String, json: String) = PiEvent(seq, type, seq, Json.parseToJsonElement(json).jsonObject)

internal val resumePrefix = listOf(
    piEvent(1, "state", """{"state":"working"}"""),
    piEvent(2, "user_message", """{"text":"hi"}"""),
    piEvent(3, "assistant_delta", """{"text":"pre"}"""),
    piEvent(4, "compaction", "{}"),
)

internal fun resumeSnapshot(): PiSessionSnapshot = snapshot(seq = 4).copy(
    checkpoint = TranscriptBuilder().apply { resumePrefix.forEach { apply(it) } }.checkpoint(),
)

internal fun resumeSummary(firstSeen: Long = 100) = piSummary(firstSeen, "session", "instance")
