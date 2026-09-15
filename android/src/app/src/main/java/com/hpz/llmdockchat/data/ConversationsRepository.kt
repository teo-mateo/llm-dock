package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.ConversationIdResponseDto
import com.hpz.llmdockchat.data.dto.ConversationListResponseDto
import com.hpz.llmdockchat.data.dto.CreateConversationRequestDto
import com.hpz.llmdockchat.data.dto.DeleteConversationsRequestDto
import com.hpz.llmdockchat.data.dto.DeleteConversationsResponseDto
import com.hpz.llmdockchat.data.dto.OkResponseDto
import com.hpz.llmdockchat.data.dto.UpdateMcpServersRequestDto
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.ConversationSummary
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * `GET/DELETE /api/chat/conversations*` (F02).
 *
 * [list] always requests `limit=-1` — the whole list as one consistent
 * snapshot. The endpoint also supports offset paging, but paging over a
 * mutable `updated_at DESC` ordering can skip or duplicate rows as threads are
 * touched between page fetches; this is a single-user dashboard with a modest
 * thread count, so the simplicity of one request wins (see F02's
 * *Deviations*).
 *
 * It also always passes `unfiled=true`: the phone has no project concept, so
 * desktop-created project threads must not appear in the flat list. The
 * server does the filtering (F02-R6).
 */
open class ConversationsRepository(private val api: ApiClient) {

    suspend fun list(): Result<List<ConversationSummary>> = apiCall {
        api.get(
            Endpoints.CONVERSATIONS,
            ConversationListResponseDto.serializer(),
            query = mapOf("limit" to "-1", "unfiled" to "true"),
        ).conversations.map { it.toDomain() }
    }

    suspend fun delete(id: String): Result<Unit> = apiCall {
        api.request(
            method = "DELETE",
            path = Endpoints.conversation(id),
            deserializer = OkResponseDto.serializer(),
        )
        Unit
    }

    /** Returns how many the server actually deleted. */
    suspend fun deleteMany(ids: List<String>): Result<Int> = apiCall {
        api.request(
            method = "POST",
            path = Endpoints.CONVERSATIONS_DELETE_BATCH,
            deserializer = DeleteConversationsResponseDto.serializer(),
            body = ApiJson.encodeToString(DeleteConversationsRequestDto(ids)),
        ).deleted
    }

    /**
     * `POST /api/chat/conversations` (F03-R1). [mainService] is the only
     * required field. [promptId] left null sends neither `prompt_id` nor
     * `main_system_prompt` — see [CreateConversationRequestDto] for why that
     * distinction is deliberate. Returns the new conversation's id.
     */
    suspend fun create(mainService: String, promptId: String? = null): Result<String> = apiCall {
        api.request(
            method = "POST",
            path = Endpoints.CONVERSATIONS,
            deserializer = ConversationIdResponseDto.serializer(),
            body = ApiJson.encodeToString(
                CreateConversationRequestDto(mainService = mainService, promptId = promptId),
            ),
        ).id
    }

    /**
     * `PUT /api/chat/conversations/<id>` with `mcp_servers_json` (F03-R3) —
     * the only way to set tools on a thread just created via [create], which
     * does not accept the field.
     *
     * `open` so a test can stand in a write whose completion order it
     * controls — the lost-update race this replaces was invisible to a
     * MockWebServer test, which answers in the order it was handed responses.
     */
    open suspend fun setMcpServers(id: String, serverIds: List<String>): Result<Unit> = apiCall {
        api.request(
            method = "PUT",
            path = Endpoints.conversation(id),
            deserializer = ConversationIdResponseDto.serializer(),
            body = ApiJson.encodeToString(
                UpdateMcpServersRequestDto(
                    mcpServersJson = ApiJson.encodeToString(ListSerializer(String.serializer()), serverIds),
                ),
            ),
        )
        Unit
    }

    /**
     * `PUT /api/chat/conversations/<id>` with `prompt_id` (F03 follow-up).
     * The id alone is the whole selection body — the server resolves the
     * content and stores its copy. Detach (`promptId == null`) adds
     * `main_system_prompt: ""` so the stored text clears to the default,
     * matching the React picker (`ChatArea.handlePromptSelect`).
     *
     * Hand-built, for the same reason as [setReasoningLevel]: with
     * `explicitNulls = false` a null DTO field is omitted, and a detach of
     * `{}` answers 200 while changing nothing. Takes effect on the next turn,
     * like every other conversation setting.
     */
    open suspend fun setPrompt(id: String, promptId: String?): Result<Unit> = apiCall {
        val body = buildJsonObject {
            put("prompt_id", promptId?.let { JsonPrimitive(it) } ?: JsonNull)
            if (promptId == null) put("main_system_prompt", JsonPrimitive(""))
        }.toString()
        api.request(
            method = "PUT",
            path = Endpoints.conversation(id),
            deserializer = ConversationIdResponseDto.serializer(),
            body = body,
        )
        Unit
    }

    /**
     * `PUT /api/chat/conversations/<id>` with `reasoning_level` (F15-R4).
     *
     * The body is hand-built as a `JsonObject`, not `ApiJson.encodeToString` of
     * a `@Serializable` DTO, and that is the whole point: this client's encoder
     * runs with `explicitNulls = false`, so a null field on a data class is
     * **omitted** — a `UpdateReasoningLevelRequestDto(null)` would be a PUT of
     * `{}`, answering 200 while clearing nothing, which is a "Model default"
     * button that looks like it works forever. The explicit `JsonNull` puts
     * `"reasoning_level": null` on the wire, which the server reads as "send no
     * reasoning field" (`chat/routes.py:update_conversation`).
     *
     * A level the service stopped offering comes back 400 with
     * `code: "invalid_reasoning_level"`, which is F15-R7's revert path.
     */
    open suspend fun setReasoningLevel(id: String, level: String?): Result<Unit> = apiCall {
        api.request(
            method = "PUT",
            path = Endpoints.conversation(id),
            deserializer = ConversationIdResponseDto.serializer(),
            body = buildJsonObject { put("reasoning_level", level?.let { JsonPrimitive(it) } ?: JsonNull) }
                .toString(),
        )
        Unit
    }
}
