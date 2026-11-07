package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.model.PiPrompt
import com.hpz.llmdockchat.feature.pi.transcript.PiSnapshotLimits
import java.io.File
import java.io.RandomAccessFile
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
class PiSessionSnapshotStoreTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `persisted snapshot survives reopen and OS eviction is a miss`() = runTest {
        val directory = temporary.newFolder()
        val original = snapshot()
        val dispatcher = StandardTestDispatcher(testScheduler)
        val store = PiSessionSnapshotStore(directory, backgroundScope, dispatcher)
        assertNull(store.read(original.identity))
        assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(store.generation(original.identity), original).await())
        assertEquals(original, store.read(original.identity))
        store.close()
        val reopened = PiSessionSnapshotStore(directory, backgroundScope, dispatcher)
        assertEquals(original, reopened.read(original.identity))
        assertTrue(File(directory, original.identity.fileName()).delete())
        assertNull(reopened.read(original.identity))
        reopened.close()
    }

    @Test
    fun `enqueue copies caller owned lists before asynchronous encoding`() = runTest {
        val directory = temporary.newFolder()
        val original = snapshot()
        val items = original.checkpoint.items.toMutableList()
        val prompts = mutableListOf(PiPrompt("prompt", "confirm", null))
        val mutable = original.copy(
            checkpoint = original.checkpoint.copy(items = items),
            summary = original.summary.copy(prompts = prompts),
        )
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler))
        val saved = store.enqueue(store.generation(original.identity), mutable)
        items.clear()
        prompts.clear()
        assertEquals(PiSnapshotWriteResult.Stored, saved.await())
        assertEquals(original, store.read(original.identity))
        store.close()
    }

    @Test
    fun `interrupted prepare or replacement preserves previous file and reports failure without orphan temp`() = runTest {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler), files = files)
        val original = snapshot()
        val generation = store.generation(original.identity)
        assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(generation, original).await())
        val bytes = File(directory, original.identity.fileName()).readBytes()
        for (interruptPrepare in listOf(true, false)) {
            files.interruptPrepare = interruptPrepare
            files.failCommit = !interruptPrepare
            val result = store.enqueue(generation, snapshot(seq = 30)).await()
            assertTrue(result is PiSnapshotWriteResult.Failed)
            assertEquals(original, store.read(original.identity))
            assertTrue(bytes.contentEquals(File(directory, original.identity.fileName()).readBytes()))
            assertEquals(listOf(original.identity.fileName()), directory.listFiles()!!.map { it.name })
        }
        store.close()
    }

    @Test
    fun `startup cleans only owned orphan temps and does not promote partial content`() = runTest {
        val directory = temporary.newFolder()
        val original = snapshot()
        val target = File(directory, original.identity.fileName()).apply { writeBytes(encodedSnapshot(original)) }
        val orphan = File(directory, target.name.removeSuffix(".json.gz") + ".tmp").apply { writeText("partial") }
        val unrelated = File(directory, "unrelated.tmp").apply { writeText("keep") }
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler))
        assertEquals(original, store.read(original.identity))
        assertFalse(orphan.exists())
        assertEquals("keep", unrelated.readText())
        store.close()
    }

    @Test
    fun `corruption wrong payload identity and oversized compressed file are normal misses`() = runTest {
        val directory = temporary.newFolder()
        val identity = snapshotIdentity()
        val file = File(directory, identity.fileName())
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler))
        runCurrent()
        for (bytes in listOf("bad gzip".toByteArray(), encodedSnapshot(snapshot(snapshotIdentity("other"))),
            encodedSnapshot(snapshot().copy(version = 99)))) {
            file.writeBytes(bytes)
            assertNull(store.read(identity))
        }
        RandomAccessFile(file, "rw").use { it.setLength(PiSnapshotLimits().committedBytes + 1) }
        assertNull(store.read(identity))
        store.close()
    }

    @Test
    fun `oversized decompressed replacement is skipped without losing prior checkpoint`() = runTest {
        val directory = temporary.newFolder()
        val store = PiSessionSnapshotStore(
            directory, backgroundScope, StandardTestDispatcher(testScheduler), limits = PiSnapshotLimits(jsonBytes = 4096),
        )
        val original = snapshot()
        val generation = store.generation(original.identity)
        assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(generation, original).await())
        assertEquals(PiSnapshotWriteResult.Skipped, store.enqueue(generation, snapshot(text = "x".repeat(4096))).await())
        assertEquals(original, store.read(original.identity))
        assertEquals(1, directory.listFiles()!!.size)
        store.close()
    }

    @Test
    fun `initialization IO failure produces read miss and explicit write failure`() = runTest {
        val notDirectory = temporary.newFile()
        val store = PiSessionSnapshotStore(notDirectory, backgroundScope, StandardTestDispatcher(testScheduler))
        val original = snapshot()
        val queued = store.enqueue(store.generation(original.identity), original)
        assertTrue(queued.await() is PiSnapshotWriteResult.Failed)
        assertNull(store.read(original.identity))
        assertTrue(store.enqueue(store.generation(original.identity), original).await() is PiSnapshotWriteResult.Failed)
        store.close()
    }

    @Test
    fun `invalid snapshot is skipped and no cache is persisted`() = runTest {
        val directory = temporary.newFolder()
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler))
        val original = snapshot().copy(lastSeq = -1)
        assertEquals(PiSnapshotWriteResult.Skipped, store.enqueue(store.generation(original.identity), original).await())
        assertNull(store.read(original.identity))
        assertTrue(directory.listFiles()!!.isEmpty())
        store.close()
    }
}
