package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.core.net.OkHttpSseTransport
import com.hpz.llmdockchat.core.net.StreamRequest
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.baseUrl
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockResponseBody
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import okio.BufferedSink
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class PiPinnedStreamTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `real outgoing cached stream sends saved cursor to captured server`() = runBlocking {
        val server = MockWebServer().also { it.start() }
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        val gate = CountDownLatch(1)
        val address = baseUrl(server.url("/").toString())
        val client = OkHttpClient.Builder().readTimeout(0, TimeUnit.MILLISECONDS).build()
        val fixture = PiRuntimeFixture(temporary.newFolder(), scope, Dispatchers.Default)
        fixture.switch(address)
        val seed = resumeSnapshot().let { it.copy(identity = it.identity.copy(server = address.value)) }
        fixture.store.enqueue(fixture.store.generation(seed.identity), seed).await()
        val transport = OkHttpSseTransport(client, FakeServerUrlStore(address), Dispatchers.IO)
        val runtime = fixture.runtime(transport, seed.identity.key)
        val frames = "data: ${kotlinx.serialization.json.Json.parseToJsonElement(resumeSummary())}\n\n"
        val tail = ": end\n\n"
        server.enqueue(MockResponse.Builder().body(object : MockResponseBody {
            override val contentLength = (frames.toByteArray().size + tail.toByteArray().size).toLong()
            override fun writeTo(sink: BufferedSink) {
                sink.writeUtf8(frames)
                sink.flush()
                if (gate.await(15, TimeUnit.SECONDS)) sink.writeUtf8(tail)
            }
        }).build())
        try {
            runtime.start(scope)
            try {
                withTimeout(10_000) { runtime.state.first { it is PiSessionUiState.Loaded && it.phase == PiSessionPhase.CONNECTED } }
            } catch (e: Exception) {
                throw AssertionError("state=${runtime.state.value}, requests=${server.requestCount}", e)
            }
            val request = server.takeRequest(5, TimeUnit.SECONDS)!!
            assertEquals("/api/pi/sessions/session/instance/stream", request.url.encodedPath)
            assertEquals("4", request.url.queryParameter("after"))
            assertEquals(address.resolve("/").host, request.url.host)
        } finally {
            runtime.stop()
            gate.countDown()
            scope.cancel()
            client.connectionPool.evictAll()
            server.close()
        }
    }

    @Test
    fun `pinned reconnect created before switch cannot send old cursor to new server`() = runBlocking {
        val first = MockWebServer().also { it.start() }
        val second = MockWebServer().also { it.start() }
        val original = baseUrl(first.url("/").toString())
        val addresses = FakeServerUrlStore(original)
        val client = OkHttpClient.Builder().readTimeout(0, TimeUnit.MILLISECONDS).build()
        val transport = OkHttpSseTransport(client, addresses, Dispatchers.IO)
        val request = StreamRequest("/api/pi/sessions/s/i/stream", query = mapOf("after" to "42"), expectedServer = original)
        first.enqueue(MockResponse.Builder().body("data: ready\n\n").build())
        try {
            assertEquals(listOf("ready"), transport.open(request).take(1).toList())
            assertEquals("42", first.takeRequest(5, TimeUnit.SECONDS)!!.url.queryParameter("after"))
            val reconnect = transport.open(request)
            addresses.set(baseUrl(second.url("/").toString()))
            val error = runCatching { reconnect.toList() }.exceptionOrNull()
            assertTrue(error is CancellationException)
            assertEquals(1, first.requestCount)
            assertEquals(0, second.requestCount)
        } finally {
            client.connectionPool.evictAll()
            first.close()
            second.close()
        }
    }
}
