package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** F11-R2's detail fetch and F11-R3/R4's start/stop calls. */
class ServicesRepositoryTest {

    private lateinit var server: MockWebServer
    private lateinit var repository: ServicesRepository

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
        repository = ServicesRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
    }

    @After
    fun tearDown() {
        server.close()
    }

    @Test
    fun `detail decodes the config and renders params as flag-value pairs`() = runBlocking {
        server.enqueue(
            MockResponse.Builder().body(
                """{"service_name": "llamacpp-a", "config": {"model_path": "/models/a.gguf",
                    "params": {"-ngl": "99", "--enable-x": ""}, "template_type": "llamacpp",
                    "model_size_str": "26.1 GB", "api_key": "secret"}}""",
            ).build(),
        )

        val config = repository.detail("llamacpp-a").getOrThrow()

        assertEquals("/models/a.gguf", config?.modelPath)
        assertEquals("llamacpp", config?.templateType)
        assertEquals("26.1 GB", config?.modelSizeStr)
        assertEquals(setOf("-ngl" to "99", "--enable-x" to ""), config?.flags?.toSet())
        val request = server.takeRequest()
        assertEquals("/api/services/llamacpp-a", request.url.encodedPath)
        assertEquals("GET", request.method)
    }

    /**
     * Bug-shaped: a `detail` that treats every non-2xx the same way would
     * surface this 404 as a generic failure, which is exactly what F11-R2's
     * fourth criterion says the detail screen must not show as an error.
     * This asserts the 404 comes back `Result.success(null)`, not a failure.
     */
    @Test
    fun `a 404 from detail is success with a null config, not a failure`() = runBlocking {
        server.enqueue(MockResponse.Builder().code(404).body("""{"error": "not found"}""").build())

        val result = repository.detail("ghost-service")

        assertTrue(result.isSuccess)
        assertNull(result.getOrThrow())
    }

    @Test
    fun `a non-404 failure from detail is a real failure`() = runBlocking {
        server.enqueue(MockResponse.Builder().code(500).body("""{"error": "Docker socket unavailable"}""").build())

        val result = repository.detail("llamacpp-a")

        assertTrue(result.isFailure)
    }

    @Test
    fun `start posts to the start endpoint`() = runBlocking {
        server.enqueue(MockResponse.Builder().body("""{"success": true}""").build())

        val result = repository.start("llamacpp-a")

        assertTrue(result.isSuccess)
        val request = server.takeRequest()
        assertEquals("/api/services/llamacpp-a/start", request.url.encodedPath)
        assertEquals("POST", request.method)
    }

    @Test
    fun `stop posts to the stop endpoint and surfaces a server failure message`() = runBlocking {
        server.enqueue(MockResponse.Builder().code(400).body("""{"error": "Container already stopped"}""").build())

        val result = repository.stop("llamacpp-a")

        assertTrue(result.isFailure)
        val request = server.takeRequest()
        assertEquals("/api/services/llamacpp-a/stop", request.url.encodedPath)
    }
}
