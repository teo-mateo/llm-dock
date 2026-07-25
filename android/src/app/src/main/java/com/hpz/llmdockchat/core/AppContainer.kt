package com.hpz.llmdockchat.core

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.core.handlers.ReplaceFileCorruptionHandler
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.preferencesDataStore
import com.hpz.llmdockchat.core.auth.AuthService
import com.hpz.llmdockchat.core.auth.CredentialReauthenticator
import com.hpz.llmdockchat.core.auth.CredentialStore
import com.hpz.llmdockchat.core.auth.DataStoreCredentialStore
import com.hpz.llmdockchat.core.auth.DataStoreTokenStore
import com.hpz.llmdockchat.core.auth.KeystoreSecretCipher
import com.hpz.llmdockchat.core.auth.ReauthenticatorHolder
import com.hpz.llmdockchat.core.auth.SecretCipher
import com.hpz.llmdockchat.core.auth.SessionManager
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
import com.hpz.llmdockchat.core.prefs.DataStoreDraftStore
import com.hpz.llmdockchat.core.prefs.DataStoreNewChatPreferences
import com.hpz.llmdockchat.core.prefs.DraftStore
import com.hpz.llmdockchat.core.prefs.NewChatPreferences
import com.hpz.llmdockchat.data.ChatRepository
import com.hpz.llmdockchat.data.ConversationsRepository
import com.hpz.llmdockchat.data.GpuStreamRepository
import com.hpz.llmdockchat.data.LogsStreamRepository
import com.hpz.llmdockchat.data.HealthRepository
import com.hpz.llmdockchat.data.McpServersRepository
import com.hpz.llmdockchat.data.OpenRouterModelsRepository
import com.hpz.llmdockchat.data.PromptsRepository
import com.hpz.llmdockchat.data.ReachabilityRepository
import com.hpz.llmdockchat.data.ServicesRepository
import com.hpz.llmdockchat.data.ServicesStreamRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import java.time.Duration

/**
 * A corrupt preferences file is replaced rather than thrown from. Everything
 * stored here — a server address, a session token and an encrypted credential —
 * is re-enterable, so recovering silently beats failing every read.
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
    cipher: SecretCipher = KeystoreSecretCipher(),
) {
    private val appScope = CoroutineScope(SupervisorJob() + dispatchers.io)
    private val dataStore = context.applicationContext.llmDockDataStore

    val sessionState = SessionState()
    val serverUrlStore: ServerUrlStore = DataStoreServerUrlStore(dataStore, appScope)
    val tokenStore: TokenStore = DataStoreTokenStore(dataStore, appScope, cipher)
    val credentialStore: CredentialStore = DataStoreCredentialStore(dataStore, appScope, cipher)

    /** Breaks the cycle: the HTTP stack exists before anything that can log in. */
    private val reauthenticatorHolder = ReauthenticatorHolder()

    private val httpClient: OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(AuthInterceptor(tokenStore, sessionState, reauthenticatorHolder))
        .authenticator(SessionAuthenticator(tokenStore, sessionState, reauthenticatorHolder))
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

    /**
     * The reachability check must not leave the user watching a spinner while a
     * wrong address runs out the ordinary 15 s connect timeout — F01-R2 allows
     * it "a few seconds".
     */
    private val probeClient: OkHttpClient = httpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .readTimeout(Duration.ofSeconds(3))
        .callTimeout(Duration.ofSeconds(5))
        .build()

    val apiClient = ApiClient(httpClient, serverUrlStore, ApiJson, dispatchers.io)
    val sseTransport: SseTransport = OkHttpSseTransport(streamingClient, serverUrlStore, dispatchers.io)

    val authService = AuthService(apiClient)
    val healthRepository = HealthRepository(
        ApiClient(probeClient, serverUrlStore, ApiJson, dispatchers.io),
    )
    val reachabilityRepository = ReachabilityRepository(healthRepository)
    val conversationsRepository = ConversationsRepository(apiClient)
    val chatRepository = ChatRepository(apiClient, sseTransport)
    val servicesRepository = ServicesRepository(apiClient)
    val servicesStreamRepository = ServicesStreamRepository(sseTransport)
    val gpuStreamRepository = GpuStreamRepository(sseTransport)
    val logsStreamRepository = LogsStreamRepository(sseTransport)
    val promptsRepository = PromptsRepository(apiClient)
    val mcpServersRepository = McpServersRepository(apiClient)
    val openRouterModelsRepository = OpenRouterModelsRepository(apiClient)
    val newChatPreferences: NewChatPreferences = DataStoreNewChatPreferences(dataStore, appScope)
    val draftStore: DraftStore = DataStoreDraftStore(dataStore, appScope)

    private val reauthenticator = CredentialReauthenticator(
        credentials = credentialStore,
        sessionState = sessionState,
        // OkHttp's `Authenticator` is a blocking callback on a network thread.
        // `/api/auth/session` is exempt from both the interceptor and the
        // authenticator, so this cannot recurse into itself.
        exchange = { credential -> runBlocking { authService.signIn(credential) } },
    )

    val sessionManager = SessionManager(
        serverUrlStore = serverUrlStore,
        tokenStore = tokenStore,
        credentials = credentialStore,
        sessionState = sessionState,
        authService = authService,
        reauthenticator = reauthenticator,
    )

    init {
        reauthenticatorHolder.delegate = reauthenticator
    }
}
