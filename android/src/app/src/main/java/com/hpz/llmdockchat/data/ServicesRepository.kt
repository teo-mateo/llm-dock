package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.ServiceListResponseDto
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.ServiceSummary

/**
 * `GET /api/services` (F03's model picker, later F10's models list). Returns
 * every compose service unfiltered — including non-chat and non-model
 * containers like `open-webui` — so each caller applies its own filter
 * ([ServiceSummary.isChatCapable] for F03) rather than this repository
 * guessing what a future feature needs.
 */
class ServicesRepository(private val api: ApiClient) {
    suspend fun list(): Result<List<ServiceSummary>> = apiCall {
        api.get(Endpoints.SERVICES, ServiceListResponseDto.serializer()).services.map { it.toDomain() }
    }
}
