package com.hpz.llmdockchat.core.prefs

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import kotlin.time.Duration.Companion.seconds

class PiTextAppearanceTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val ioScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    @After
    fun tearDown() {
        ioScope.cancel()
    }

    private fun dataStore(file: File): DataStore<Preferences> =
        PreferenceDataStoreFactory.create(scope = ioScope, produceFile = { file })

    private fun appearance(store: DataStore<Preferences>) =
        DataStorePiTextAppearance(store, ioScope)

    private suspend fun readBack(store: DataStore<Preferences>): String? =
        store.data.first()[stringPreferencesKey(KEY)]

    private suspend fun PiTextAppearance.awaitScale(expected: Float): Float =
        withContext(Dispatchers.Default) {
            withTimeout(5.seconds) { scale.first { it == expected } }
        }

    // Writes reach disk through ValuePreference's serialising channel, so the
    // in-memory value lands before the file does. Asserting the number on disk
    // means waiting for that write rather than racing it.
    private suspend fun awaitDisk(store: DataStore<Preferences>, expected: String): String? =
        withContext(Dispatchers.Default) {
            withTimeout(5.seconds) {
                var value = readBack(store)
                while (value != expected) {
                    delay(25)
                    value = readBack(store)
                }
                value
            }
        }

    private fun file(name: String) = folder.newFile(name)

    @Test
    fun `an unset preference reads as the default size`() = runTest {
        val appearance = appearance(dataStore(file("unset.preferences_pb")))
        assertEquals(PiTextAppearance.DEFAULT, appearance.awaitScale(PiTextAppearance.DEFAULT), 0.0001f)
    }

    @Test
    fun `a chosen size lands on disk as the plain number a restart reads back`() = runTest {
        val store = dataStore(file("restart.preferences_pb"))
        val written = appearance(store)
        written.setScale(0.8f)
        assertEquals(0.8f, written.awaitScale(0.8f), 0.0001f)
        assertEquals("0.8", awaitDisk(store, "0.8"))

        // A second reader over the same file is what process restart does for
        // the stored value: the number on disk, run through the same decoder.
        assertEquals(0.8f, appearance(store).awaitScale(0.8f), 0.0001f)
    }

    @Test
    fun `reset writes the default and a reopened reader reports it as default`() = runTest {
        val store = dataStore(file("reset.preferences_pb"))
        val written = appearance(store)
        written.setScale(0.7f)
        written.awaitScale(0.7f)

        written.setScale(PiTextAppearance.DEFAULT)
        assertEquals("1.0", awaitDisk(store, "1.0"))
        assertTrue(PiTextAppearance.isDefault(appearance(store).awaitScale(PiTextAppearance.DEFAULT)))
    }

    @Test
    fun `a stored value outside the range is clamped on the way in`() = runTest {
        val store = dataStore(file("hostile.preferences_pb"))
        store.edit { it[stringPreferencesKey(KEY)] = "2.5" }
        assertEquals(PiTextAppearance.MAX, appearance(store).awaitScale(PiTextAppearance.MAX), 0.0001f)
    }

    @Test
    fun `a write below the floor lands on the floor and above the ceiling on the ceiling`() {
        val appearance = InMemoryPiTextAppearance()
        appearance.setScale(0.1f)
        assertEquals(PiTextAppearance.MIN, appearance.scale.value, 0.0001f)
        appearance.setScale(9f)
        assertEquals(PiTextAppearance.MAX, appearance.scale.value, 0.0001f)
    }

    @Test
    fun `stepping up from the floor reaches the default exactly`() {
        var scale = PiTextAppearance.MIN
        repeat(3) { scale = PiTextAppearance.clampToStep(scale + PiTextAppearance.STEP) }
        assertEquals(PiTextAppearance.DEFAULT, scale, 0.0001f)
        assertTrue(PiTextAppearance.isDefault(scale))
    }

    @Test
    fun `a value off the grid is pulled onto it so reset is not offered at default`() {
        assertEquals(PiTextAppearance.DEFAULT, PiTextAppearance.clampToStep(0.9999999f), 0.0001f)
        assertFalse(PiTextAppearance.isDefault(PiTextAppearance.clampToStep(1.1f)))
    }

    @Test
    fun `the readout is a whole percentage`() {
        assertEquals("100%", PiTextAppearance.label(1.0f))
        assertEquals("70%", PiTextAppearance.label(0.7f))
        assertEquals("140%", PiTextAppearance.label(1.4f))
    }

    @Test
    fun `the range leaves room below the default`() {
        assertTrue(PiTextAppearance.MIN < PiTextAppearance.DEFAULT)
        assertTrue(PiTextAppearance.MAX > PiTextAppearance.DEFAULT)
    }

    private companion object {
        const val KEY = "pi_response_text_scale"
    }
}
