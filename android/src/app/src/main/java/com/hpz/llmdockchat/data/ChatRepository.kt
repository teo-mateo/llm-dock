package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.RunEvent
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.core.net.StreamRequest
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.core.net.parseFrame
import com.hpz.llmdockchat.data.dto.CancelRunRequestDto
import com.hpz.llmdockchat.data.dto.CancelRunResponseDto
import com.hpz.llmdockchat.data.dto.ConversationDetailDto
import com.hpz.llmdockchat.data.dto.SendMessageRequestDto
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.ConversationDetail
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.encodeToString

/**
 * A thread and the runs that happen in it (F04).
 *
 * The three run-producing endpoints emit the same frames, so they share one
 * reader: [send], [editAndResend] and [reattach] differ only in the request
 * they open, never in how the stream is interpreted.
 *
 * None of the stream functions cancels anything server-side. Collecting stops
 * when the collector goes away; the run keeps going and persists its reply
 * (F04-R10). Cancelling is [cancelActiveRun] and nothing else.
 */
class ChatRepository(
    private val api: ApiClient,
    private val transport: SseTransport,
) {

    suspend fun load(conversationId: String): Result<ConversationDetail> = apiCall {
        api.get(
            Endpoints.conversation(conversationId),
            ConversationDetailDto.serializer(),
        ).toDomain()
    }

    /**
     * `POST /api/chat/conversations/<id>/messages`. The response body *is* the
     * run's SSE stream, so a 409 (a run is already active) surfaces as the
     * flow's first and only failure, before any frame.
     */
    fun send(conversationId: String, content: String, images: List<String> = emptyList()): Flow<RunEvent> =
        runStream(
            StreamRequest(
                path = Endpoints.conversationMessages(conversationId),
                method = "POST",
                body = ApiJson.encodeToString(
                    SendMessageRequestDto(content = content, images = images.takeIf { it.isNotEmpty() }),
                ),
            ),
        )

    /** `PUT …/messages/<msg_id>` — edit and re-run, used by F06. Same frames. */
    fun editAndResend(
        conversationId: String,
        messageId: String,
        content: String,
        images: List<String> = emptyList(),
    ): Flow<RunEvent> = runStream(
        StreamRequest(
            path = Endpoints.conversationMessage(conversationId, messageId),
            method = "PUT",
            body = ApiJson.encodeToString(
                SendMessageRequestDto(content = content, images = images.takeIf { it.isNotEmpty() }),
            ),
        ),
    )

    /**
     * `GET /api/chat/runs/<id>/stream` — replay then live tail, used by F09.
     * Present here because it is the third producer of the same frames and
     * proving that with the reattach fixtures is what makes "one reader" true
     * rather than asserted.
     */
    fun reattach(runId: String): Flow<RunEvent> =
        runStream(StreamRequest(path = Endpoints.runStream(runId)))

    /**
     * Cancel by conversation, not by run id (F04-R6): the server always knows a
     * conversation's active run, so Stop works even before `run_started` was
     * seen. [expectedRunId] stops a stale Stop from killing a newer run.
     *
     * A no-op is a 200 with `{"run": null}` — cancelling a run that already
     * finished is not an error.
     */
    suspend fun cancelActiveRun(conversationId: String, expectedRunId: String?): Result<Unit> = apiCall {
        api.request(
            method = "POST",
            path = Endpoints.cancelActiveRun(conversationId),
            deserializer = CancelRunResponseDto.serializer(),
            body = ApiJson.encodeToString(CancelRunRequestDto(expectedRunId)),
        )
        Unit
    }

    private fun runStream(request: StreamRequest): Flow<RunEvent> =
        transport.open(request).map(::parseFrame)
}
