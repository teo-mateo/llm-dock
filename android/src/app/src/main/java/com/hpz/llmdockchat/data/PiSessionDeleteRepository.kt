package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.ServerUrlStore
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.Endpoints
import com.hpz.llmdockchat.core.net.apiCall
import com.hpz.llmdockchat.data.dto.PiSessionDeletedResponseDto
import com.hpz.llmdockchat.data.model.PiSessionKey
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * `DELETE /api/pi/sessions/<session>/<instance>` — drops the dashboard's
 * capture of one session: its row, its events, its prompts and its commands.
 *
 * A session the extension is still heartbeating for comes back 409: the next
 * hello re-inserts the row, so deleting it live would only hide a session that
 * is about to reappear.
 */
open class PiSessionDeleteRepository(
    private val api: ApiClient,
    private val serverUrlStore: ServerUrlStore? = null,
    private val onDeleted: (BaseUrl, PiSessionKey) -> Unit = { _, _ -> },
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO,
) {

    open suspend fun delete(key: PiSessionKey): Result<Unit> = withContext(ioDispatcher) {
        apiCall {
            val server = serverUrlStore?.current()
            api.request(
                method = "DELETE",
                server = server,
                path = Endpoints.piSession(key.sessionId, key.instanceId),
                deserializer = PiSessionDeletedResponseDto.serializer(),
            )
            if (server != null) onDeleted(server, key)
            Unit
        }
    }
}
