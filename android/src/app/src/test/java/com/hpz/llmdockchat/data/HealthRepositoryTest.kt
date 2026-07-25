package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiException
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.readFixture
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** `GET /api/health` end to end: base URL, request building, decode, mapping. */
class HealthRepositoryTest {

    private lateinit var server: MockWebServer
    private lateinit var urlStore: FakeServerUrlStore
    private lateinit var repository: HealthRepository

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        urlStore = FakeServerUrlStore(
            (BaseUrl.normalize(server.url("/").toString()) as BaseUrlResult.Valid).baseUrl,
        )
        val client = OkHttpClient.Builder()
            // No token stored: health must still go through.
            .addInterceptor(AuthInterceptor(FakeTokenStore(null), SessionState()))
            .build()
        repository = HealthRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
    }

    @After
    fun tearDown() {
        server.close()
    }

    @Test
    fun `a recorded dashboard response maps to the domain model`() = runTest {
        server.enqueue(MockResponse.Builder().body(readFixture("health.json")).build())

        val health = repository.health().getOrThrow()

        assertTrue(health.healthy)
        assertEquals("healthy", health.status)
        assertEquals("1.0.0", health.version)
        assertTrue(health.dockerAvailable)
        assertTrue(health.nvidiaAvailable)
        assertEquals("/api/health", server.takeRequest().url.encodedPath)
    }

    @Test
    fun `the request is built from whatever base URL is stored right now`() = runTest {
        server.enqueue(MockResponse.Builder().body(readFixture("health.json")).build())
        repository.health().getOrThrow()
        server.takeRequest()

        val other = MockWebServer()
        other.start()
        other.enqueue(MockResponse.Builder().body(readFixture("health.json")).build())
        urlStore.set((BaseUrl.normalize(other.url("/api").toString()) as BaseUrlResult.Valid).baseUrl)

        repository.health().getOrThrow()

        assertEquals(1, server.requestCount)
        assertEquals("/api/health", other.takeRequest().url.encodedPath)
        other.close()
    }

    @Test
    fun `an unknown field the dashboard adds later does not break decoding`() = runTest {
        server.enqueue(
            MockResponse.Builder()
                .body("""{"status":"healthy","version":"1.1.0","brand_new_field":[1,2,3]}""")
                .build(),
        )
        val health = repository.health().getOrThrow()
        assertTrue(health.healthy)
        assertEquals("1.1.0", health.version)
    }

    @Test
    fun `an unhealthy status is carried, not thrown away`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"status":"degraded"}""").build())
        val health = repository.health().getOrThrow()
        assertEquals(false, health.healthy)
        assertEquals("degraded", health.status)
        assertNull(health.version)
    }

    @Test
    fun `a failing server surfaces its own message`() = runTest {
        server.enqueue(
            MockResponse.Builder().code(503).body("""{"error": "Docker socket unavailable"}""").build(),
        )

        val error = (repository.health().exceptionOrNull() as ApiException).error
        error as AppError.Http
        assertEquals(503, error.status)
        assertEquals("Docker socket unavailable", error.message)
    }

    @Test
    fun `a response that is not the expected shape is a parse failure`() = runTest {
        server.enqueue(MockResponse.Builder().body("<html>not the dashboard</html>").build())
        val error = (repository.health().exceptionOrNull() as ApiException).error
        assertTrue(error is AppError.Parse)
    }

    @Test
    fun `an unreachable server is a network failure`() = runTest {
        server.close()
        val error = (repository.health().exceptionOrNull() as ApiException).error
        assertTrue(error is AppError.Network)
    }
}
