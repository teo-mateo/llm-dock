package com.hpz.llmdockchat.testing

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.data.PiSessionDeleteRepository
import com.hpz.llmdockchat.data.model.PiSessionKey
import kotlinx.coroutines.Dispatchers
import okhttp3.OkHttpClient

class FakePiSessionDeleteRepository : PiSessionDeleteRepository(
    ApiClient(
        OkHttpClient.Builder().build(),
        FakeServerUrlStore(BaseUrl.restore("http://localhost")!!),
        ApiJson,
        Dispatchers.IO,
    ),
) {
    val deleted = mutableListOf<PiSessionKey>()
    var failure: Throwable? = null

    override suspend fun delete(key: PiSessionKey): Result<Unit> {
        deleted += key
        failure?.let { return Result.failure(it) }
        return Result.success(Unit)
    }
}
