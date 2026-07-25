package com.hpz.llmdockchat.core.prefs

import androidx.datastore.core.DataStore
import androidx.datastore.core.handlers.ReplaceFileCorruptionHandler
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import kotlin.time.Duration.Companion.seconds

class ValuePreferenceTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val ioScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val key = "server_base_url"

    @After
    fun tearDown() {
        ioScope.cancel()
    }

    private fun file(name: String = "test.preferences_pb"): File = folder.newFile(name)

    private fun dataStore(
        file: File,
        recoverFromCorruption: Boolean = false,
    ): DataStore<Preferences> = PreferenceDataStoreFactory.create(
        corruptionHandler = if (recoverFromCorruption) {
            ReplaceFileCorruptionHandler { emptyPreferences() }
        } else {
            null
        },
        scope = ioScope,
        produceFile = { file },
    )

    private fun preference(
        store: DataStore<Preferences>,
        scope: CoroutineScope = ioScope,
    ) = ValuePreference(
        dataStore = store,
        name = key,
        scope = scope,
        decode = { it },
        encode = { it },
    )

    /**
     * Reads through the same DataStore instance — a second one over the same
     * file is rejected outright. `edit` only completes once the file has been
     * rewritten, so this reflects what landed on disk, in the order it landed.
     */
    private suspend fun readBack(store: DataStore<Preferences>): String? =
        store.data.first()[stringPreferencesKey(key)]

    // Off the test dispatcher deliberately: the disk read takes real time, and
    // runTest's virtual clock would blow straight through the timeout.
    private suspend fun ValuePreference<String>.awaitReady(): String? =
        withContext(Dispatchers.Default) {
            withTimeout(5.seconds) { flow.first { it is Stored.Ready }.valueOrNull }
        }

    // -- reading -----------------------------------------------------------

    @Test
    fun `the value is Loading until the disk read lands`() = runTest {
        val file = file()
        val store = dataStore(file)
        store.put(key, "http://10.0.2.2:3399")

        // A dispatcher that has not been advanced: the hydration coroutine is
        // queued but has provably not run.
        val pref = preference(store, CoroutineScope(StandardTestDispatcher(testScheduler)))

        assertEquals(Stored.Loading, pref.flow.value)
    }

    @Test
    fun `the stored value is reported once read`() = runTest {
        val file = file()
        val store = dataStore(file)
        store.put(key, "http://10.0.2.2:3399")

        assertEquals("http://10.0.2.2:3399", preference(store).awaitReady())
    }

    @Test
    fun `an absent value settles as Ready null, not Loading forever`() = runTest {
        val pref = preference(dataStore(file()))
        assertNull(pref.awaitReady())
        assertTrue(pref.flow.value is Stored.Ready)
    }

    @Test
    fun `the blocking read returns the stored value for callers off a coroutine`() {
        val file = folder.newFile("blocking.preferences_pb")
        val store = dataStore(file)
        kotlinx.coroutines.runBlocking { store.put(key, "totp-abc") }

        val pref = preference(store)

        // What the OkHttp interceptor does: no coroutine, needs an answer now.
        assertEquals("totp-abc", pref.get())
        assertEquals("totp-abc", pref.get())
    }

    // -- the corrupt-file path --------------------------------------------

    @Test
    fun `an unreadable file settles as empty rather than failing every read`() = runTest {
        val file = file("corrupt.preferences_pb")
        file.writeBytes(byteArrayOf(1, 2, 3, 4, 5, 6, 7, 8))

        val pref = preference(dataStore(file, recoverFromCorruption = false))

        assertNull(pref.awaitReady())
        // The old failure mode: hydration never completes, so every later
        // access retries the throwing read. These must not throw, and must
        // not block.
        assertNull(pref.get())
        assertNull(pref.get())
        assertTrue(pref.flow.value is Stored.Ready)
    }

    @Test
    fun `a corrupt file is replaced when the corruption handler is installed`() = runTest {
        val file = file("replaced.preferences_pb")
        file.writeBytes(byteArrayOf(9, 9, 9, 9))

        val store = dataStore(file, recoverFromCorruption = true)
        val pref = preference(store)
        assertNull(pref.awaitReady())

        pref.set("http://dock.lan:3399")
        pref.awaitPendingWrites()

        assertEquals("http://dock.lan:3399", readBack(store))
        assertTrue(file.readBytes().decodeToString().contains("http://dock.lan:3399"))
    }

    // -- write ordering ----------------------------------------------------

    @Test
    fun `clear followed by set leaves the newer value on disk`() = runTest {
        val file = file()
        val store = dataStore(file)
        val pref = preference(store)
        pref.awaitReady()

        pref.set("totp-stale")
        pref.awaitPendingWrites()

        // Exactly what SessionAuthenticator does on a 401.
        pref.clear()
        pref.set("totp-fresh")
        pref.awaitPendingWrites()

        assertEquals("totp-fresh", pref.get())
        assertEquals("totp-fresh", readBack(store))
        val onDisk = file.readBytes().decodeToString()
        assertTrue("the losing clear() won", onDisk.contains("totp-fresh"))
    }

    @Test
    fun `a burst of writes reaches disk in call order`() = runTest {
        val store = dataStore(file())
        val pref = preference(store)
        pref.awaitReady()

        repeat(50) { pref.set("value-$it") }
        pref.clear()
        pref.set("last")
        pref.awaitPendingWrites()

        assertEquals("last", readBack(store))
    }

    @Test
    fun `a set that beats the first read is not clobbered by it`() = runTest {
        val file = file()
        val store = dataStore(file)
        store.put(key, "on-disk")

        val pref = preference(store, CoroutineScope(StandardTestDispatcher(testScheduler)))
        // Hydration is queued but has not run; write before it does.
        pref.set("just-signed-in")

        assertEquals(Stored.Ready("just-signed-in"), pref.flow.value)
        testScheduler.advanceUntilIdle()
        assertEquals(Stored.Ready("just-signed-in"), pref.flow.value)
    }

    private suspend fun DataStore<Preferences>.put(name: String, value: String) {
        edit { it[stringPreferencesKey(name)] = value }
    }
}
