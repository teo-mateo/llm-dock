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
import org.junit.Assert.assertFalse
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
    fun `list requests unfiled=true so project threads never appear`() = runTest {
        server.enqueue(MockResponse.Builder().body(readFixture("conversations.json")).build())
        repository.list().getOrThrow()

        val request: RecordedRequest = server.takeRequest()
        assertEquals("true", request.url.queryParameter("unfiled"))
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

    // -- create (F03-R1, F03-R2) --

    @Test
    fun `create with only a model sends just main_service`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"id": "new-conv"}""").build())

        val id = repository.create(mainService = "llamacpp-gemma-4-26b-a4b-it-q8").getOrThrow()

        assertEquals("new-conv", id)
        val body = server.takeRequest().body?.utf8().orEmpty()
        assertEquals("""{"main_service":"llamacpp-gemma-4-26b-a4b-it-q8"}""", body)
    }

    @Test
    fun `create with a named prompt sends prompt_id and omits main_system_prompt`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"id": "new-conv"}""").build())

        repository.create(mainService = "llamacpp-gemma-4-26b-a4b-it-q8", promptId = "c2efe71a-cd7b").getOrThrow()

        val body = server.takeRequest().body?.utf8().orEmpty()
        assertEquals(
            """{"main_service":"llamacpp-gemma-4-26b-a4b-it-q8","prompt_id":"c2efe71a-cd7b"}""",
            body,
        )
        assertFalse(body.contains("main_system_prompt"))
    }

    /**
     * The load-bearing case (F03-R2): "Default" must send NEITHER `prompt_id`
     * NOR `main_system_prompt` — not nulls, not empty strings — so the server
     * falls back to its own configured default rather than treating an
     * explicit empty prompt as the conversation's system prompt.
     */
    @Test
    fun `create with the Default prompt choice omits both prompt_id and main_system_prompt`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"id": "new-conv"}""").build())

        repository.create(mainService = "llamacpp-gemma-4-26b-a4b-it-q8", promptId = null).getOrThrow()

        val body = server.takeRequest().body?.utf8().orEmpty()
        assertEquals("""{"main_service":"llamacpp-gemma-4-26b-a4b-it-q8"}""", body)
        assertFalse(body.contains("prompt_id"))
        assertFalse(body.contains("main_system_prompt"))
    }

    @Test
    fun `a failed create surfaces the server's own message`() = runTest {
        server.enqueue(MockResponse.Builder().code(400).body("""{"error": "main_service is required"}""").build())

        val error = repository.create(mainService = "").exceptionOrNull() as ApiException
        val http = error.error as com.hpz.llmdockchat.core.error.AppError.Http
        assertEquals("main_service is required", http.message)
    }

    // -- setMcpServers (F03-R3) --

    @Test
    fun `setMcpServers PUTs mcp_servers_json as a JSON-encoded array string`() = runTest {
        server.enqueue(MockResponse.Builder().body("""{"id": "conv-1"}""").build())

        repository.setMcpServers("conv-1", listOf("sympy-math", "websearch")).getOrThrow()

        val request = server.takeRequest()
        assertEquals("PUT", request.method)
        assertEquals("/api/chat/conversations/conv-1", request.url.encodedPath)
        assertEquals(
            """{"mcp_servers_json":"[\"sympy-math\",\"websearch\"]"}""",
            request.body?.utf8().orEmpty(),
        )
    }
}
