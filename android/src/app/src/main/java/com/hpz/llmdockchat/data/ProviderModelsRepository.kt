package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.ProviderModelsResponseDto
import com.hpz.llmdockchat.data.mapper.toGroups
import com.hpz.llmdockchat.data.model.ProviderGroup

/**
 * Read-only and keyless (F16-R4): the provider settings endpoints carry API
 * keys and edit server config, so this app never calls them.
 */
class ProviderModelsRepository(private val api: ApiClient) {
    suspend fun list(): Result<List<ProviderGroup>> = apiCall {
        api.get(Endpoints.PROVIDER_MODELS, ProviderModelsResponseDto.serializer()).toGroups()
    }
}
