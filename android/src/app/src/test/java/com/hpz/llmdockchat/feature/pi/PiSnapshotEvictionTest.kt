package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotLimits
import java.io.File
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

@OptIn(ExperimentalCoroutinesApi::class)
class PiSnapshotEvictionTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `default policy keeps eight entries and successful reads refresh persistent access LRU`() = runTest {
        val directory = temporary.newFolder()
        var time = 1_000L
        val dispatcher = StandardTestDispatcher(testScheduler)
        var store = PiSessionSnapshotStore(directory, backgroundScope, dispatcher, clock = { time })
        val snapshots = (0..8).map { snapshot(snapshotIdentity("s$it")) }
        snapshots.take(8).forEach {
            assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(store.generation(it.identity), it).await())
            time += 1_000
        }
        assertEquals(8, directory.listFiles()!!.size)
        val savedAt = snapshots[0].savedAt
        assertEquals(snapshots[0], store.read(snapshots[0].identity))
        assertEquals(time, File(directory, snapshots[0].identity.fileName()).lastModified())
        assertEquals(savedAt, store.read(snapshots[0].identity)!!.savedAt)
        store.close()
        time += 1_000
        store = PiSessionSnapshotStore(directory, backgroundScope, dispatcher, clock = { time })
        assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(store.generation(snapshots[8].identity), snapshots[8]).await())
        assertEquals(8, directory.listFiles()!!.size)
        assertNull(store.read(snapshots[1].identity))
        for (index in listOf(0, 2, 3, 4, 5, 6, 7, 8)) assertEquals(snapshots[index], store.read(snapshots[index].identity))
        store.close()
    }

    @Test
    fun `committed byte quota includes compressed files and evicts before atomic commit`() = runTest {
        val directory = temporary.newFolder()
        val first = snapshot(snapshotIdentity("first"))
        val second = snapshot(snapshotIdentity("second"))
        val third = snapshot(snapshotIdentity("third"))
        val budget = encodedSnapshot(first).size.toLong() + encodedSnapshot(second).size
        var time = 1_000L
        val store = PiSessionSnapshotStore(
            directory, backgroundScope, StandardTestDispatcher(testScheduler), clock = { time },
            limits = PiSnapshotLimits(committedBytes = budget),
        )
        for (snapshot in listOf(first, second)) {
            assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(store.generation(snapshot.identity), snapshot).await())
            time += 1_000
        }
        assertEquals(budget, directory.listFiles()!!.sumOf { it.length() })
        store.read(first.identity)
        time += 1_000
        assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(store.generation(third.identity), third).await())
        assertTrue(directory.listFiles()!!.sumOf { it.length() } <= budget)
        assertEquals(first, store.read(first.identity))
        assertNull(store.read(second.identity))
        assertEquals(third, store.read(third.identity))
        store.close()
    }

    @Test
    fun `replacement excludes old target from projected entry count`() = runTest {
        val directory = temporary.newFolder()
        val store = PiSessionSnapshotStore(
            directory, backgroundScope, StandardTestDispatcher(testScheduler), limits = PiSnapshotLimits(entries = 2),
        )
        val first = snapshot(snapshotIdentity("first"))
        val second = snapshot(snapshotIdentity("second"))
        for (snapshot in listOf(first, second, first.copy(lastSeq = 30))) {
            assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(store.generation(snapshot.identity), snapshot).await())
        }
        assertEquals(2, directory.listFiles()!!.size)
        assertEquals(30L, store.read(first.identity)?.lastSeq)
        assertEquals(second, store.read(second.identity))
        store.close()
    }

    @Test
    fun `startup enforces quotas deterministically when access times tie`() = runTest {
        val directory = temporary.newFolder()
        val snapshots = (1..9).map { snapshot(snapshotIdentity("s$it")) }
        snapshots.forEach { snapshot ->
            File(directory, snapshot.identity.fileName()).apply {
                writeBytes(encodedSnapshot(snapshot))
                assertTrue(setLastModified(1_000))
            }
        }
        val victim = snapshots.minBy { it.identity.fileName() }
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler))
        runCurrent()
        assertEquals(8, directory.listFiles()!!.size)
        assertNull(store.read(victim.identity))
        store.close()
    }
}
