package com.hpz.llmdockchat.core.auth

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.stringPreferencesKey
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.testing.SoftwareSecretCipher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

/**
 * The Keystore itself needs a device, so these run the same AES/GCM
 * construction against a JVM-resident key. What they prove is the part that
 * belongs to this class: plaintext never reaches DataStore, a round trip
 * survives a cold start, and an unopenable blob degrades to "no credential".
 */
class CredentialStoreTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val password = "correct-horse-battery-staple"

    /**
     * One DataStore per file at a time — a second live instance over the same
     * path is an error DataStore raises rather than tolerates. Cancelling the
     * scope releases the file, which is also what makes "reopen it" a fair
     * imitation of a cold app start.
     */
    private fun <T> session(file: File, cipher: SecretCipher, block: suspend Session.() -> T): T =
        runBlocking {
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
            try {
                val store = PreferenceDataStoreFactory.create(scope = scope, produceFile = { file })
                withTimeout(15_000) {
                    Session(
                        store,
                        DataStoreCredentialStore(store, scope, cipher),
                        DataStoreTokenStore(store, scope, cipher),
                    ).block()
                }
            } finally {
                scope.cancel()
            }
        }

    private class Session(
        val dataStore: DataStore<Preferences>,
        val credentials: DataStoreCredentialStore,
        val tokens: DataStoreTokenStore,
    ) {
        suspend fun raw(key: String): String? = dataStore.data.first()[stringPreferencesKey(key)]
    }

    @Test
    fun `a credential round-trips through a cold start`() {
        val file = folder.newFile("creds.preferences_pb")
        val cipher = SoftwareSecretCipher()

        session(file, cipher) {
            credentials.save(Credential.Password(password))
            credentials.awaitPendingWrites()
        }

        session(file, cipher) {
            assertEquals(Credential.Password(password), credentials.current())
            assertEquals(Stored.Ready(true), credentials.hasCredential.first { it is Stored.Ready })
        }
    }

    @Test
    fun `nothing recognisable reaches disk`() {
        val file = folder.newFile("creds.preferences_pb")

        val persisted = session(file, SoftwareSecretCipher()) {
            credentials.save(Credential.Password(password))
            credentials.awaitPendingWrites()
            raw("credential")
        }

        assertNotNull(persisted)
        assertFalse(persisted!!.contains(password))
        assertFalse("the credential kind is a tag inside the ciphertext", persisted.contains("password"))
        assertFalse(file.readBytes().toString(Charsets.ISO_8859_1).contains(password))
    }

    @Test
    fun `signing out leaves nothing behind`() {
        val file = folder.newFile("creds.preferences_pb")
        val cipher = SoftwareSecretCipher()

        val persisted = session(file, cipher) {
            credentials.save(Credential.Password(password))
            credentials.awaitPendingWrites()
            credentials.clear()
            credentials.awaitPendingWrites()
            raw("credential")
        }

        assertNull(persisted)
        session(file, cipher) { assertNull(credentials.current()) }
    }

    /**
     * A restored backup, or a Keystore whose key has gone, leaves ciphertext
     * that cannot be opened. Reading it as "no credential" costs one sign-in;
     * throwing would cost the app its ability to start at all.
     */
    @Test
    fun `an undecryptable blob reads as no credential`() {
        val file = folder.newFile("creds.preferences_pb")

        session(file, SoftwareSecretCipher()) {
            credentials.save(Credential.Password(password))
            credentials.awaitPendingWrites()
        }

        session(file, SoftwareSecretCipher()) {
            assertNull(credentials.current())
            assertEquals(Stored.Ready(false), credentials.hasCredential.first { it is Stored.Ready })
        }
    }

    @Test
    fun `the session token is encrypted at rest too`() {
        val file = folder.newFile("token.preferences_pb")
        val cipher = SoftwareSecretCipher()

        val persisted = session(file, cipher) {
            tokens.update("totp-abcdefghijklmnop")
            tokens.awaitPendingWrites()
            raw("session_token")
        }

        assertNotNull(persisted)
        assertFalse(persisted!!.contains("totp-"))
        session(file, cipher) { assertEquals("totp-abcdefghijklmnop", tokens.current()) }
    }

    @Test
    fun `the credential never prints itself`() {
        val rendered = "a credential: ${Credential.Password(password)}"
        assertFalse(rendered.contains(password))
        assertTrue(rendered.contains("***"))
    }
}
