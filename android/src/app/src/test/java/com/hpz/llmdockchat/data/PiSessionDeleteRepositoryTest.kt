package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

class PiSessionDeleteRepositoryTest {

    private lateinit var server: MockWebServer
    private lateinit var repository: PiSessionDeleteRepository

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        val urlStore = FakeServerUrlStore(
            (BaseUrl.normalize(server.url("/").toString()) as BaseUrlResult.Valid).baseUrl,
        )
        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(FakeTokenStore("totp-test"), SessionState()))
            .build()
        repository = PiSessionDeleteRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
    }

    @After
    fun tearDown() {
        server.close()
    }

    @Test
    fun `delete calls DELETE on the session's own path`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"deleted": true}""").build())

        repository.delete(PiSessionKey("s1", "i1")).getOrThrow()

        val request = server.takeRequest()
        assertEquals("DELETE", request.method)
        assertEquals("/api/pi/sessions/s1/i1", request.url.encodedPath)
    }

    @Test
    fun `a live session comes back as the 409 the caller maps`() = runTest {
        server.enqueue(MockResponse.Builder().code(409).body("""{"error": "pi_session_live"}""").build())

        val error = repository.delete(PiSessionKey("s1", "i1")).exceptionOrNull()
            as com.hpz.llmdockchat.core.net.ApiException

        val http = error.error as AppError.Http
        assertEquals(409, http.status)
        assertEquals("pi_session_live", http.message)
    }
}
