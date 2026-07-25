package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.auth.SessionState
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
import mockwebserver3.RecordedRequest
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** `GET/DELETE /api/chat/conversations*` end to end (F02). */
class ConversationsRepositoryTest {

    private lateinit var server: MockWebServer
    private lateinit var repository: ConversationsRepository

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
        repository = ConversationsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
    }

    @After
    fun tearDown() {
        server.close()
    }

    @Test
    fun `a recorded dashboard response maps every row to the domain model`() = runTest {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())

        val conversations = repository.list().getOrThrow()

        assertEquals(2, conversations.size)
        assertEquals("5ebf5a99-e1d7-421d-86be-c16d1d53d166", conversations[0].id)
        assertEquals("llamacpp-gemma-4-26b-a4b-it-q8", (conversations[0].modelRef as com.hpz.llmdockchat.data.model.ModelRef.Local).serviceName)
        assertEquals(false, conversations[0].isGenerating)
    }

    @Test
    fun `list requests limit=-1, the one-shot consistent snapshot`() = runTest {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        repository.list().getOrThrow()

        val request: RecordedRequest = server.takeRequest()
        assertEquals("/api/chat/conversations", request.url.encodedPath)
        assertEquals("-1", request.url.queryParameter("limit"))
    }

    @Test
    fun `delete calls DELETE on the conversation's own path`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"ok": true}""").build())

        repository.delete("conv-1").getOrThrow()

        val request = server.takeRequest()
        assertEquals("DELETE", request.method)
        assertEquals("/api/chat/conversations/conv-1", request.url.encodedPath)
    }

    @Test
    fun `a 404 delete surfaces the server's own message`() = runTest {
        server.enqueue(
            MockResponse.Builder().code(404).body("""{"error": "Conversation not found"}""").build(),
        )

        val error = repository.delete("gone").exceptionOrNull() as ApiException
        val http = error.error as com.hpz.llmdockchat.core.error.AppError.Http
        assertEquals("Conversation not found", http.message)
    }

    @Test
    fun `batch delete posts ids and returns how many were removed`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"ok": true, "deleted": 2}""").build())

        val deleted = repository.deleteMany(listOf("a", "b")).getOrThrow()

        assertEquals(2, deleted)
        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/chat/conversations/delete", request.url.encodedPath)
        assertTrue(request.body?.utf8().orEmpty().contains(""""ids":["a","b"]"""))
    }
}
