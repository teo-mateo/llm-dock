package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.PromptListResponseDto
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.ManagedPrompt

/** `GET /api/chat/prompts` (F03-R2). Read-only — creating/editing prompts is
 * dashboard Tools-page work, out of scope on the phone. */
class PromptsRepository(private val api: ApiClient) {
    suspend fun list(): Result<List<ManagedPrompt>> = apiCall {
        api.get(Endpoints.PROMPTS, PromptListResponseDto.serializer()).prompts.map { it.toDomain() }
    }
}
