package com.hpz.llmdockchat.core.auth

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.prefs.ValuePreference
import com.hpz.llmdockchat.core.prefs.valueOrNull
import com.hpz.llmdockchat.core.net.ServerUrlStore
import com.hpz.llmdockchat.core.net.BaseUrl
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn

/**
 * The current session bearer token. Sessions live in a process-memory dict on
 * the dashboard, so this is disposable: losing it costs one re-authentication,
 * not any user data.
 *
 * [CredentialStore] owns the long-lived *credential* the token is derived from.
 */
interface TokenStore {
    val token: StateFlow<Stored<String>>

    /** Blocks until the first disk read lands; for network threads only. */
    fun current(): String?
    fun current(server: BaseUrl?): String? = current()
    fun update(token: String, server: BaseUrl? = null)
    fun clear()
    fun clear(server: BaseUrl?) = clear()
}

/**
 * Encrypted at rest alongside the credential. The token is disposable,
 * but it is a working bearer for eight sliding hours, so it gets the same
 * treatment rather than sitting in plain preferences.
 */
class DataStoreTokenStore(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
    cipher: SecretCipher,
    private val serverUrlStore: ServerUrlStore,
) : TokenStore {

    private val pref = ValuePreference(
        dataStore = dataStore,
        name = "session_token",
        scope = scope,
        decode = { stored -> cipher.decrypt(stored)?.let { raw ->
            ServerBoundSecret.decode(raw) { it.takeIf(String::isNotBlank) }
        } },
        encode = { bound -> cipher.encrypt(bound.encode { it }).orEmpty() },
    )

    override val token: StateFlow<Stored<String>> = combine(pref.flow, serverUrlStore.baseUrl) { secret, server ->
        when {
            secret is Stored.Loading || server is Stored.Loading -> Stored.Loading
            else -> Stored.Ready(secret.valueOrNull?.takeIf { it.server == server.valueOrNull }?.secret)
        }
    }.stateIn(scope, SharingStarted.Eagerly, Stored.Loading)

    override fun current(): String? = current(serverUrlStore.current())
    override fun current(server: BaseUrl?): String? = pref.get()?.takeIf { it.server == server }?.secret
    override fun update(token: String, server: BaseUrl?) {
        val target = checkNotNull(server ?: serverUrlStore.current())
        serverUrlStore.ifCurrent(target) { pref.set(ServerBoundSecret(target, token)) }
    }
    override fun clear() = pref.clear()
    override fun clear(server: BaseUrl?) {
        if (server != null) serverUrlStore.ifCurrent(server) {
            pref.clearIf { it.server == server }
        }
    }

    /** Test support: writes are enqueued, so "on disk yet?" needs a join. */
    internal suspend fun awaitPendingWrites() = pref.awaitPendingWrites()
}
