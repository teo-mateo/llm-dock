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

/**
 * `GET/DELETE /api/chat/conversations*` (F02).
 *
 * [list] always requests `limit=-1` — the whole list as one consistent
 * snapshot. The endpoint also supports offset paging, but paging over a
 * mutable `updated_at DESC` ordering can skip or duplicate rows as threads are
 * touched between page fetches; this is a single-user dashboard with a modest
 * thread count, so the simplicity of one request wins (see F02's
 * *Deviations*).
 */
class ConversationsRepository(private val api: ApiClient) {

    suspend fun list(): Result<List<ConversationSummary>> = apiCall {
        api.get(
            Endpoints.CONVERSATIONS,
            ConversationListResponseDto.serializer(),
            query = mapOf("limit" to "-1"),
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
     */
    suspend fun setMcpServers(id: String, serverIds: List<String>): Result<Unit> = apiCall {
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
}
