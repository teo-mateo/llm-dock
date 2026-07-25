package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.baseUrl
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Duration

class ReachabilityRepositoryTest {

    private fun repository(url: String, client: OkHttpClient = OkHttpClient()) =
        ReachabilityRepository(
            HealthRepository(
                ApiClient(
                    client.newBuilder()
                        .addInterceptor(AuthInterceptor(FakeTokenStore(), SessionState()))
                        .connectTimeout(Duration.ofSeconds(3))
                        .build(),
                    FakeServerUrlStore(baseUrl(url)),
                    ApiJson,
                    Dispatchers.IO,
                ),
            ),
        )

    @Test
    fun `the dashboard identifies itself`() = runBlocking {
        val server = MockWebServer()
        server.start()
        server.enqueue(MockResponse.Builder().body("""{"status": "healthy"}""").build())

        val result = repository(server.url("/").toString()).probe()

        assertEquals(Reachability.Dashboard, result)
        assertEquals("/api/health", server.takeRequest().url.encodedPath)
        server.close()
    }

    /** The model server on `api.ai.heapzilla.eu` answers /api/health like this. */
    @Test
    fun `something else answering is not a dashboard`() = runBlocking {
        val server = MockWebServer()
        server.start()
        server.enqueue(
            MockResponse.Builder().body("""{"error": {"message": "Invalid API Key"}}""").build(),
        )

        assertTrue(repository(server.url("/").toString()).probe() is Reachability.NotADashboard)
        server.close()
    }

    @Test
    fun `a page of HTML is not a dashboard either`() = runBlocking {
        val server = MockWebServer()
        server.start()
        server.enqueue(MockResponse.Builder().body("<html><body>nginx</body></html>").build())

        assertTrue(repository(server.url("/").toString()).probe() is Reachability.NotADashboard)
        server.close()
    }

    /** F01-R2: a wrong host has to read as unreachable, not as a wrong code. */
    @Test
    fun `nothing listening reads as unreachable`() = runBlocking {
        val server = MockWebServer()
        server.start()
        val url = server.url("/").toString()
        server.close()

        assertTrue(repository(url).probe() is Reachability.Unreachable)
    }
}
