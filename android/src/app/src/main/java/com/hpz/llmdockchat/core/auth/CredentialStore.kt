package com.hpz.llmdockchat.core.auth

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.prefs.ValuePreference
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
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

    fun save(credential: Credential)
    fun clear()
}

class DataStoreCredentialStore(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
    cipher: SecretCipher,
) : CredentialStore {

    private val pref = ValuePreference(
        dataStore = dataStore,
        name = "credential",
        scope = scope,
        // A blob that will not decrypt — a restored backup, a reset Keystore —
        // reads as "no credential" rather than as an error. The cost is one
        // sign-in, and the alternative is an app that cannot start.
        decode = { stored -> cipher.decrypt(stored)?.let(Credential::decode) },
        encode = { credential -> cipher.encrypt(Credential.encode(credential)).orEmpty() },
    )

    override val hasCredential: StateFlow<Stored<Boolean>> = pref.flow
        .map { stored ->
            when (stored) {
                Stored.Loading -> Stored.Loading
                is Stored.Ready -> Stored.Ready(stored.value != null)
            }
        }
        .stateIn(scope, SharingStarted.Eagerly, Stored.Loading)

    override fun current(): Credential? = pref.get()
    override fun save(credential: Credential) = pref.set(credential)
    override fun clear() = pref.clear()

    /** Test support: writes are enqueued, so "on disk yet?" needs a join. */
    internal suspend fun awaitPendingWrites() = pref.awaitPendingWrites()
}
