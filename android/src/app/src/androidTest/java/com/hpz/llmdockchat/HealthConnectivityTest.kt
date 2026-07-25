package com.hpz.llmdockchat

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.auth.TokenStore
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.net.BaseUrlResult
import com.hpz.llmdockchat.core.net.ServerUrlStore
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.prefs.valueOrNull
import com.hpz.llmdockchat.data.HealthRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The one test that needs both a device and the live dashboard: proves the HTTP
 * stack reaches `10.0.2.2:3399` from inside the emulator and decodes what comes
 * back. Everything else about the stack is covered by JVM tests.
 *
 * Requires the dashboard to be running on the host.
 */
@RunWith(AndroidJUnit4::class)
class HealthConnectivityTest {

    @Test
    fun theDashboardAnswersHealthOverTheRealStack() = runBlocking {
        val base = BaseUrl.normalize("http://10.0.2.2:3399/api/") as BaseUrlResult.Valid
        assertEquals("http://10.0.2.2:3399", base.baseUrl.value)

        val urlHolder = MutableStateFlow<Stored<BaseUrl>>(Stored.Ready(base.baseUrl))
        val urlStore = object : ServerUrlStore {
            override val baseUrl: StateFlow<Stored<BaseUrl>> = urlHolder
            override fun current(): BaseUrl? = urlHolder.value.valueOrNull
            override fun set(url: BaseUrl) { urlHolder.value = Stored.Ready(url) }
            override fun clear() { urlHolder.value = Stored.Ready(null) }
        }
        // No token at all: /api/health is exempt, so this must still work.
        val tokenHolder = MutableStateFlow<Stored<String>>(Stored.Ready(null))
        val tokenStore = object : TokenStore {
            override val token: StateFlow<Stored<String>> = tokenHolder
            override fun current(): String? = tokenHolder.value.valueOrNull
            override fun update(token: String) { tokenHolder.value = Stored.Ready(token) }
            override fun clear() { tokenHolder.value = Stored.Ready(null) }
        }

        val client = OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(tokenStore, SessionState()))
            .build()
        val repository = HealthRepository(ApiClient(client, urlStore, ApiJson, Dispatchers.IO))

        val health = repository.health().getOrThrow()

        assertTrue("dashboard reported ${health.status}", health.healthy)
        assertTrue(health.version?.isNotBlank() == true)
    }
}
