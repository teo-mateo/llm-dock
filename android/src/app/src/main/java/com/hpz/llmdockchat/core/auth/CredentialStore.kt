package com.hpz.llmdockchat.core.auth

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.prefs.ValuePreference
import com.hpz.llmdockchat.core.prefs.valueOrNull
import com.hpz.llmdockchat.core.net.ServerUrlStore
import com.hpz.llmdockchat.core.net.BaseUrl
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn

/**
 * The credential that survives a dead session token (F01-R5). Encrypted at
 * rest by construction: the store never sees plaintext on disk, only what
 * [SecretCipher] hands it.
 *
 * Only [hasCredential] is exposed as a flow. The secret itself is reachable
 * through [current] alone, which the HTTP stack calls on a network thread —
 * nothing observable by the UI ever holds it.
 */
interface CredentialStore {

    /** Whether a credential is stored, once the disk read has landed. */
    val hasCredential: StateFlow<Stored<Boolean>>

    /** Blocks until the first disk read lands; for network threads only. */
    fun current(): Credential?
    fun current(server: BaseUrl?): Credential? = current()

    fun save(credential: Credential, server: BaseUrl? = null)
    fun clear()
    fun clear(server: BaseUrl?) = clear()
}

class DataStoreCredentialStore(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
    cipher: SecretCipher,
    private val serverUrlStore: ServerUrlStore,
) : CredentialStore {

    private val pref = ValuePreference(
        dataStore = dataStore,
        name = "credential",
        scope = scope,
        // A blob that will not decrypt — a restored backup, a reset Keystore —
        // reads as "no credential" rather than as an error. The cost is one
        // sign-in, and the alternative is an app that cannot start.
        decode = { stored -> cipher.decrypt(stored)?.let { raw ->
            ServerBoundSecret.decode(raw, Credential::decode)
        } },
        encode = { bound -> cipher.encrypt(bound.encode(Credential::encode)).orEmpty() },
    )

    override val hasCredential: StateFlow<Stored<Boolean>> = combine(pref.flow, serverUrlStore.baseUrl) { secret, server ->
        when {
            secret is Stored.Loading || server is Stored.Loading -> Stored.Loading
            else -> Stored.Ready(secret.valueOrNull?.server == server.valueOrNull && secret.valueOrNull != null)
        }
    }.stateIn(scope, SharingStarted.Eagerly, Stored.Loading)

    override fun current(): Credential? = current(serverUrlStore.current())
    override fun current(server: BaseUrl?): Credential? = pref.get()?.takeIf { it.server == server }?.secret
    override fun save(credential: Credential, server: BaseUrl?) {
        val target = checkNotNull(server ?: serverUrlStore.current())
        serverUrlStore.ifCurrent(target) { pref.set(ServerBoundSecret(target, credential)) }
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
