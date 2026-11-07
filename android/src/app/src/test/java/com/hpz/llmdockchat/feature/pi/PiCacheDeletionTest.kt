package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.data.PiSessionDeleteRepository
import com.hpz.llmdockchat.data.PiSessionsRepository
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.baseUrl
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockResponseBody
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import okio.BufferedSink
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

@OptIn(ExperimentalCoroutinesApi::class)
class PiCacheDeletionTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `successful REST deletion invalidates active and prepared writes while rejected deletion preserves cache`() = runTest {
        val server = MockWebServer().also { it.start() }
        try {
            for (status in listOf(200, 409)) {
                val directory = temporary.newFolder()
                val files = ControlledPiSnapshotFiles(directory)
                val fixture = PiRuntimeFixture(directory, backgroundScope, StandardTestDispatcher(testScheduler), { currentTime }, files)
                val address = baseUrl(server.url("/").toString())
                fixture.switch(address)
                val seed = resumeSnapshot().let { it.copy(identity = it.identity.copy(server = address.value)) }
                fixture.store.enqueue(fixture.store.generation(seed.identity), seed).await()
                val gate = SnapshotWriteGate().also { files.gate = it }
                val transport = DrivenPiTransport()
                val runtime = fixture.runtime(transport, seed.identity.key)
                runtime.start(backgroundScope)
                runCurrent()
                transport.send(piBatch(9, "suffix")); transport.send(resumeSummary())
                gate.prepared.await()
                val addresses = FakeServerUrlStore(address)
                val repository = PiSessionDeleteRepository(
                    ApiClient(OkHttpClient(), addresses, ApiJson, Dispatchers.IO), addresses, fixture.cache::remove,
                )
                server.enqueue(MockResponse.Builder().code(status)
                    .body(if (status == 200) """{"deleted":true}""" else """{"error":"pi_session_live"}""").build())
                assertEquals(status == 200, repository.delete(seed.identity.key).isSuccess)
                runCurrent()
                val request = server.takeRequest(5, TimeUnit.SECONDS)!!
                assertEquals("DELETE", request.method)
                assertEquals("/api/pi/sessions/session/instance", request.url.encodedPath)
                if (status == 200) assertSame(PiSessionUiState.Unknown, runtime.state.value)
                gate.release.complete(Unit)
                runCurrent()
                if (status == 200) assertNull(fixture.store.read(seed.identity))
                else assertEquals(9L, fixture.store.read(seed.identity)?.lastSeq)
                runtime.stop()
            }
        } finally {
            server.close()
        }
    }

    @Test
    fun `list removed callback deletes the captured namespace and cannot resurrect prepared detail write`() = runTest {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val fixture = PiRuntimeFixture(directory, backgroundScope, StandardTestDispatcher(testScheduler), { currentTime }, files)
        val seed = resumeSnapshot()
        fixture.store.enqueue(fixture.store.generation(seed.identity), seed).await()
        val gate = SnapshotWriteGate().also { files.gate = it }
        val transport = DrivenPiTransport()
        val runtime = fixture.runtime(transport, seed.identity.key)
        runtime.start(backgroundScope)
        runCurrent()
        transport.send(piBatch(9, "suffix")); transport.send(resumeSummary())
        gate.prepared.await()
        val listTransport = DrivenPiTransport()
        listTransport.send("""{"type":"session_removed","session_id":"session","instance_id":"instance"}""")
        PiSessionsRepository(listTransport, FakeServerUrlStore(fixture.server), fixture.cache::remove)
            .streamWithStatus().take(1).toList()
        assertEquals(fixture.server, listTransport.requests.single().expectedServer)
        assertSame(PiSessionUiState.Unknown, runtime.state.value)
        gate.release.complete(Unit)
        runCurrent()
        assertNull(fixture.store.read(seed.identity))
        assertTrue(directory.listFiles()!!.isEmpty())
    }

    @Test
    fun `delete response arriving after server switch only invalidates its original namespace`() = runTest {
        val first = MockWebServer().also { it.start() }
        val second = MockWebServer().also { it.start() }
        val release = CountDownLatch(1)
        try {
            val addressA = baseUrl(first.url("/").toString())
            val addressB = baseUrl(second.url("/").toString())
            val addresses = FakeServerUrlStore(addressA)
            val fixture = PiRuntimeFixture(temporary.newFolder(), backgroundScope, StandardTestDispatcher(testScheduler), { currentTime })
            fixture.switch(addressA)
            val seedA = resumeSnapshot().let { it.copy(identity = it.identity.copy(server = addressA.value)) }
            val seedB = seedA.copy(identity = seedA.identity.copy(server = addressB.value))
            for (seed in listOf(seedA, seedB)) fixture.store.enqueue(fixture.store.generation(seed.identity), seed).await()
            val repository = PiSessionDeleteRepository(
                ApiClient(OkHttpClient(), addresses, ApiJson, Dispatchers.IO), addresses, fixture.cache::remove,
            )
            first.enqueue(MockResponse.Builder().body(object : MockResponseBody {
                override val contentLength = """{"deleted":true}""".toByteArray().size.toLong()
                override fun writeTo(sink: BufferedSink) {
                    check(release.await(10, TimeUnit.SECONDS))
                    sink.writeUtf8("""{"deleted":true}""")
                    sink.flush()
                }
            }).build())
            val deletion = async(Dispatchers.IO) { repository.delete(seedA.identity.key) }
            assertEquals("DELETE", first.takeRequest(5, TimeUnit.SECONDS)!!.method)
            addresses.set(addressB)
            fixture.switch(addressB)
            release.countDown()
            val outcome = deletion.await()
            assertTrue("failure=${(outcome.exceptionOrNull() as? com.hpz.llmdockchat.core.net.ApiException)?.error}", outcome.isSuccess)
            runCurrent()
            assertNull(fixture.store.read(seedA.identity))
            assertEquals(seedB, fixture.store.read(seedB.identity))
            assertEquals(0, second.requestCount)
        } finally {
            release.countDown()
            first.close()
            second.close()
        }
    }
}
