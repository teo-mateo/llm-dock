package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.testing.FakeServerUrlStore
import com.hpz.llmdockchat.testing.FakeTokenStore
import com.hpz.llmdockchat.testing.readFixture
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ProviderModelsRepositoryTest {

    private lateinit var server: MockWebServer
    private lateinit var repository: ProviderModelsRepository

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
        repository = ProviderModelsRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))
    }

    @After
    fun tearDown() {
        server.close()
    }

    @Test
    fun `the list is one authenticated GET of the models endpoint`() {
        server.enqueue(MockResponse.Builder().body(readFixture("provider_models.json")).build())

        val groups = runBlocking { repository.list() }.getOrThrow()

        assertEquals(listOf("Mistral"), groups.map { it.name })
        val request = server.takeRequest()
        assertEquals("GET", request.method)
        assertEquals("/api/chat/providers/models", request.url.encodedPath)
        assertEquals("Bearer totp-test", request.headers["Authorization"])
    }

    @Test
    fun `a server failure is a failed result, not an exception`() {
        server.enqueue(MockResponse.Builder().code(500).body("""{"error":"boom"}""").build())

        assertTrue(runBlocking { repository.list() }.isFailure)
    }

    @Test
    fun `no source file calls a provider settings endpoint or writes to a provider endpoint`() {
        val sources = File("src/main/java").walkTopDown().filter { it.extension == "kt" }.toList()
        assertTrue(sources.size > 50)
        val text = sources.associateWith { it.readText() }

        assertTrue(text.none { (_, body) -> body.contains("settings/providers") })
        val providerPaths = text.values.flatMap { Regex("\"/api/chat/providers[^\"]*\"").findAll(it).map { m -> m.value } }
        assertEquals(listOf("\"/api/chat/providers/models\""), providerPaths)
        val repositorySource = text.entries.single { it.key.name == "ProviderModelsRepository.kt" }.value
        assertTrue(repositorySource.contains("api.get(") && !repositorySource.contains("api.request("))
        val usages = text.filterValues { it.contains("Endpoints.PROVIDER_MODELS") }.keys.map { it.name }
        assertEquals(listOf("ProviderModelsRepository.kt"), usages)
    }
}
