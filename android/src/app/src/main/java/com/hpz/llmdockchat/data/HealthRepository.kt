package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.HealthDto
import com.hpz.llmdockchat.data.mapper.toDomain
import com.hpz.llmdockchat.data.model.ServerHealth

/**
 * `GET /api/health` — the one endpoint F00 wires end-to-end. Unauthenticated,
 * so it also serves as F01's reachability check for a server URL the user has
 * typed but not yet signed in to.
 */
class HealthRepository(private val api: ApiClient) {

    suspend fun health(): Result<ServerHealth> = apiCall {
        api.get(Endpoints.HEALTH, HealthDto.serializer()).toDomain()
    }
}
