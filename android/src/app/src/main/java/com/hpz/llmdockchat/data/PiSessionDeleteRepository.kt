package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.PiSessionDeletedResponseDto
import com.hpz.llmdockchat.data.model.PiSessionKey

/**
 * `DELETE /api/pi/sessions/<session>/<instance>` — drops the dashboard's
 * capture of one session: its row, its events, its prompts and its commands.
 *
 * A session the extension is still heartbeating for comes back 409: the next
 * hello re-inserts the row, so deleting it live would only hide a session that
 * is about to reappear.
 */
open class PiSessionDeleteRepository(private val api: ApiClient) {

    open suspend fun delete(key: PiSessionKey): Result<Unit> = apiCall {
        api.request(
            method = "DELETE",
            path = Endpoints.piSession(key.sessionId, key.instanceId),
            deserializer = PiSessionDeletedResponseDto.serializer(),
        )
        Unit
    }
}
