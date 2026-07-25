package com.hpz.llmdockchat.core.auth

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.prefs.ValuePreference
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.StateFlow

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
    fun update(token: String)
    fun clear()
}

/**
 * Encrypted at rest alongside the credential (F01-R5). The token is disposable,
 * but it is a working bearer for eight sliding hours, so it gets the same
 * treatment rather than sitting in plain preferences.
 */
class DataStoreTokenStore(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
    cipher: SecretCipher,
) : TokenStore {

    private val pref = ValuePreference(
        dataStore = dataStore,
        name = "session_token",
        scope = scope,
        decode = { stored -> cipher.decrypt(stored)?.takeIf(String::isNotBlank) },
        encode = { token -> cipher.encrypt(token).orEmpty() },
    )

    override val token: StateFlow<Stored<String>> get() = pref.flow
    override fun current(): String? = pref.get()
    override fun update(token: String) = pref.set(token)
    override fun clear() = pref.clear()

    /** Test support: writes are enqueued, so "on disk yet?" needs a join. */
    internal suspend fun awaitPendingWrites() = pref.awaitPendingWrites()
}
