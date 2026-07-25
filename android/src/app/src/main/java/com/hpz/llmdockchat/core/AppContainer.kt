package com.hpz.llmdockchat.core

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.core.handlers.ReplaceFileCorruptionHandler
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.preferencesDataStore
import com.hpz.llmdockchat.core.auth.DataStoreTokenStore
import com.hpz.llmdockchat.core.auth.ReauthenticatorHolder
import com.hpz.llmdockchat.core.auth.SessionState
import com.hpz.llmdockchat.core.auth.TokenStore
import com.hpz.llmdockchat.core.net.ApiClient
import com.hpz.llmdockchat.core.net.ApiJson
import com.hpz.llmdockchat.core.net.AuthInterceptor
import com.hpz.llmdockchat.core.net.DataStoreServerUrlStore
import com.hpz.llmdockchat.core.net.OkHttpSseTransport
import com.hpz.llmdockchat.core.net.ServerUrlStore
import com.hpz.llmdockchat.core.net.SessionAuthenticator
import com.hpz.llmdockchat.core.net.SseTransport
import com.hpz.llmdockchat.data.HealthRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import okhttp3.OkHttpClient
import java.time.Duration

/**
 * A corrupt preferences file is replaced rather than thrown from. Everything
 * stored here — a server address and a disposable session token — is
 * re-enterable, so recovering silently beats failing every read.
 */
private val Context.llmDockDataStore: DataStore<Preferences> by preferencesDataStore(
    name = "llm_dock",
    corruptionHandler = ReplaceFileCorruptionHandler { emptyPreferences() },
)

/**
 * The whole object graph, built once in `Application` (Architecture D9). Manual
 * because the graph is this small; Hilt stays available if it stops being.
 */
class AppContainer(
    context: Context,
    val dispatchers: AppDispatchers = AppDispatchers(),
) {
    private val appScope = CoroutineScope(SupervisorJob() + dispatchers.io)
    private val dataStore = context.applicationContext.llmDockDataStore

    val sessionState = SessionState()
    val serverUrlStore: ServerUrlStore = DataStoreServerUrlStore(dataStore, appScope)
    val tokenStore: TokenStore = DataStoreTokenStore(dataStore, appScope)

    /** F01 installs the real credential exchange here. */
    val reauthenticator = ReauthenticatorHolder()

    private val httpClient: OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(AuthInterceptor(tokenStore, sessionState))
        .authenticator(SessionAuthenticator(tokenStore, sessionState, reauthenticator))
        .connectTimeout(Duration.ofSeconds(15))
        .readTimeout(Duration.ofSeconds(30))
        .build()

    /**
     * Shares the connection pool and dispatcher, but never times out a read:
     * a stream can be quiet for minutes between keepalives.
     */
    private val streamingClient: OkHttpClient = httpClient.newBuilder()
        .readTimeout(Duration.ZERO)
        .build()

    val apiClient = ApiClient(httpClient, serverUrlStore, ApiJson, dispatchers.io)
    val sseTransport: SseTransport = OkHttpSseTransport(streamingClient, serverUrlStore, dispatchers.io)
    val healthRepository = HealthRepository(apiClient)
}
