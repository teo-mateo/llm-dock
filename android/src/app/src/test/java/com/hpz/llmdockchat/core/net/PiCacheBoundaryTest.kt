package com.hpz.llmdockchat.core.net

import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.testing.baseUrl
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class PiCacheBoundaryTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `server mutations invalidate synchronously after the captured value changes`() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        try {
            val data = PreferenceDataStoreFactory.create(scope = scope, produceFile = {
                File(temporary.root, "server.preferences_pb")
            })
            val observed = mutableListOf<BaseUrl?>()
            lateinit var urls: DataStoreServerUrlStore
            urls = DataStoreServerUrlStore(data, scope) { observed += urls.current() }
            urls.current()
            val first = baseUrl("https://first.example")
            val second = baseUrl("https://second.example")
            urls.set(first)
            assertEquals(listOf(first), observed)
            urls.set(first)
            assertEquals(1, observed.size)
            urls.set(second)
            urls.clear()
            assertEquals(listOf(first, second, null), observed)
        } finally {
            scope.coroutineContext[Job]!!.cancelAndJoin()
        }
    }

    @Test
    fun `auth loss invalidates synchronously while ordinary renewal does not`() {
        var calls = 0
        val auth = SessionState { calls++ }
        auth.requireAuthentication("expired")
        assertTrue(auth.authenticationRequired.value)
        assertEquals(1, calls)
        auth.authenticated()
        assertEquals(1, calls)
        auth.signedOut()
        assertEquals(2, calls)
    }
}
