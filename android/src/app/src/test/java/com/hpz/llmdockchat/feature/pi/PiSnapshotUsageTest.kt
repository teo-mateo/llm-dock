package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.model.PiSession
import com.hpz.llmdockchat.data.model.PiSessionKey
import com.hpz.llmdockchat.data.model.PiState
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotLimits
import java.io.File
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

@OptIn(ExperimentalCoroutinesApi::class)
class PiSnapshotUsageTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `store keeps every session without evicting`() = runTest {
        val directory = temporary.newFolder()
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler))
        val snapshots = (0 until 12).map { snapshot(snapshotIdentity("s$it")) }
        snapshots.forEach {
            assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(store.generation(it.identity), it).await())
        }
        assertEquals(12, directory.listFiles()!!.size)
        snapshots.forEach { assertEquals(it, store.read(it.identity)) }
        store.close()
    }

    @Test
    fun `usage tracks committed files across startup, write and delete`() = runTest {
        val directory = temporary.newFolder()
        val existing = snapshot(snapshotIdentity("existing"))
        File(directory, existing.identity.fileName()).writeBytes(encodedSnapshot(existing))
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler))
        runCurrent()
        assertEquals(encodedSnapshot(existing).size.toLong(), store.usage.value.bytesFor(existing.identity))

        val added = snapshot(snapshotIdentity("added"))
        store.enqueue(store.generation(added.identity), added).await()
        assertEquals(directory.listFiles()!!.sumOf { it.length() }, store.usage.value.totalBytes)
        assertTrue(store.usage.value.bytesFor(added.identity)!! > 0)

        store.delete(existing.identity)
        assertNull(store.usage.value.bytesFor(existing.identity))
        assertEquals(setOf(added.identity.fileName()), store.usage.value.files.keys)
        store.close()
    }

    @Test
    fun `usage warns only above the warning threshold`() = runTest {
        val directory = temporary.newFolder()
        val first = snapshot(snapshotIdentity("first"))
        val threshold = encodedSnapshot(first).size.toLong()
        val store = PiSessionSnapshotStore(
            directory, backgroundScope, StandardTestDispatcher(testScheduler),
            limits = PiSnapshotLimits(warningBytes = threshold),
        )
        store.enqueue(store.generation(first.identity), first).await()
        assertFalse(store.usage.value.overWarning)
        val second = snapshot(snapshotIdentity("second"))
        store.enqueue(store.generation(second.identity), second).await()
        assertTrue(store.usage.value.overWarning)
        store.close()
    }

    @Test
    fun `labels name cached sessions and the warning`() {
        val cached = session("cached")
        val missing = session("missing")
        val usage = PiCacheUsage(files = mapOf("a" to 600L * 1024 * 1024), warningBytes = 500L * 1024 * 1024)
        val labels = piCacheLabels(usage, listOf(cached, missing)) { if (it == cached.key) 2048L else null }
        assertEquals(mapOf(cached.key to "2 KB"), labels.sizes)
        assertEquals("Pi cache uses 600.0 MB on this phone (warning above 500.0 MB)", labels.warning)
        assertNull(piCacheLabels(PiCacheUsage(warningBytes = 1), emptyList()) { null }.warning)
    }

    private fun session(id: String) = PiSession(
        key = PiSessionKey(id, "i"), name = null, cwd = "/", model = null, thinkingLevel = null,
        firstSeen = 0, lastSeen = 0, endedAt = null, endReason = null, live = true,
        state = PiState.IDLE, contextPercent = null,
    )
}
