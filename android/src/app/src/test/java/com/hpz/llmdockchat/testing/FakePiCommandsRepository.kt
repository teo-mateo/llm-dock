package com.hpz.llmdockchat.testing

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.data.PiCommandsRepository
import com.hpz.llmdockchat.data.model.PiCommandOutcome
import com.hpz.llmdockchat.data.model.PiSessionKey
import kotlinx.coroutines.Dispatchers
import okhttp3.OkHttpClient

class FakePiCommandsRepository : PiCommandsRepository(
    ApiClient(
        OkHttpClient.Builder().build(),
        FakeServerUrlStore(BaseUrl.restore("http://localhost")!!),
        ApiJson,
        Dispatchers.IO,
    ),
) {
    var sendOutcome: PiCommandOutcome = PiCommandOutcome.Done
    var sentText: String? = null
    var abortCalled = false
    var sentServer: BaseUrl? = null
    var abortServer: BaseUrl? = null

    override suspend fun send(key: PiSessionKey, text: String, server: BaseUrl?): PiCommandOutcome {
        sentServer = server
        sentText = text
        return sendOutcome
    }

    override suspend fun abort(key: PiSessionKey, server: BaseUrl?): PiCommandOutcome {
        abortServer = server
        abortCalled = true
        return PiCommandOutcome.Done
    }
}
