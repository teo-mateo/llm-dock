package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.OpenRouterModelsSettingsResponseDto
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.OpenRouterAvailability

/**
 * `GET /api/chat/settings/openrouter-models` (F03). Read-only from the
 * phone — never call the PUT/DELETE variants of this endpoint here; editing
 * the curated list is dashboard Tools-page work.
 */
class OpenRouterModelsRepository(private val api: ApiClient) {
    suspend fun list(): Result<OpenRouterAvailability> = apiCall {
        val dto = api.get(Endpoints.OPENROUTER_MODELS_SETTINGS, OpenRouterModelsSettingsResponseDto.serializer())
        OpenRouterAvailability(configured = dto.configured, models = dto.current.map { it.toDomain() })
    }
}
