package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.data.model.PiCommandOutcome
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.data.model.Rejection
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

class PiCommandsRepositoryTest {

    private lateinit var server: MockWebServer
    private lateinit var repository: PiCommandsRepository

    private val key = PiSessionKey("s1", "i1")

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
        repository = PiCommandsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
    }

    @After
    fun tearDown() {
        server.close()
    }

    @Test
    fun `200 ok is Done`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"command_id":"cmd-1","ok":true,"error":null}""").build())

        assertEquals(PiCommandOutcome.Done, repository.send(key, "hello"))
    }

    @Test
    fun `200 ok false is Failed with error`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"command_id":"cmd-1","ok":false,"error":"no model"}""").build())

        assertEquals(PiCommandOutcome.Failed("no model"), repository.send(key, "hello"))
    }

    @Test
    fun `202 is Pending`() = runTest {
        server.enqueue(MockResponse.Builder().code(202).body("""{"command_id":"cmd-1","pending":true}""").build())

        assertEquals(PiCommandOutcome.Pending, repository.send(key, "hello"))
    }

    @Test
    fun `409 is Rejected OFFLINE`() = runTest {
        server.enqueue(MockResponse.Builder().code(409).body("""{"error":"pi_session_offline"}""").build())

        assertEquals(PiCommandOutcome.Rejected(Rejection.OFFLINE), repository.send(key, "hello"))
    }

    @Test
    fun `429 is RATE_LIMITED`() = runTest {
        server.enqueue(MockResponse.Builder().code(429).body("""{"error":"rate_limited"}""").build())

        assertEquals(PiCommandOutcome.Rejected(Rejection.RATE_LIMITED), repository.send(key, "hello"))
    }

    @Test
    fun `503 is BUSY`() = runTest {
        server.enqueue(MockResponse.Builder().code(503).body("""{"error":"queue_full"}""").build())

        assertEquals(PiCommandOutcome.Rejected(Rejection.BUSY), repository.send(key, "hello"))
    }

    @Test
    fun `400 invalid_text is INVALID_TEXT`() = runTest {
        server.enqueue(MockResponse.Builder().code(400).body("""{"error":"invalid_text"}""").build())

        assertEquals(PiCommandOutcome.Rejected(Rejection.INVALID_TEXT), repository.send(key, "hello"))
    }

    @Test
    fun `posts text as json`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"command_id":"cmd-1","ok":true,"error":null}""").build())

        repository.send(key, "hello")

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/pi/sessions/s1/i1/messages", request.url.encodedPath)
        assertEquals("""{"text":"hello"}""", request.body?.utf8())
    }

    @Test
    fun `abort posts to the abort path`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"command_id":"cmd-1","ok":true,"error":null}""").build())

        assertEquals(PiCommandOutcome.Done, repository.abort(key))

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/pi/sessions/s1/i1/abort", request.url.encodedPath)
        assertEquals("{}", request.body?.utf8())
    }

    @Test
    fun `unknown 400 is OTHER and carries no wire text`() = runTest {
        server.enqueue(MockResponse.Builder().code(400).body("""{"error":"invalid_body"}""").build())

        assertEquals(PiCommandOutcome.Rejected(Rejection.OTHER), repository.send(key, "hello"))
    }
}
