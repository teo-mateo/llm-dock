package com.hpz.llmdockchat.feature.pi

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
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
class PiSnapshotWriterTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun `single writer coalesces pending snapshots per key without replacing inflight state`() = runTest {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val gate = SnapshotWriteGate().also { files.gate = it }
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler), files = files)
        val identity = snapshotIdentity()
        val generation = store.generation(identity)
        val first = store.enqueue(generation, snapshot(seq = 1))
        gate.prepared.await()
        val superseded = store.enqueue(generation, snapshot(seq = 2))
        val latest = store.enqueue(generation, snapshot(seq = 3))
        val other = snapshot(snapshotIdentity("other"))
        val otherResult = store.enqueue(store.generation(other.identity), other)
        assertEquals(PiSnapshotWriteResult.Superseded, superseded.await())
        assertTrue(!first.isCompleted && !latest.isCompleted && !otherResult.isCompleted)
        assertEquals(1, files.activePreparations)
        assertEquals(1, directory.listFiles()!!.count { it.extension == "tmp" })
        gate.release.complete(Unit)
        assertEquals(PiSnapshotWriteResult.Stored, first.await())
        assertEquals(PiSnapshotWriteResult.Stored, latest.await())
        assertEquals(PiSnapshotWriteResult.Stored, otherResult.await())
        assertEquals(3L, store.read(identity)?.lastSeq)
        assertEquals(other, store.read(other.identity))
        assertEquals(1, files.maxPreparations)
        assertEquals(3, files.commits.size)
        store.close()
    }

    @Test
    fun `pending key capacity is bounded but a full queue still accepts same key replacement`() = runTest {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val gate = SnapshotWriteGate().also { files.gate = it }
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler), files = files)
        val initial = snapshot()
        val first = store.enqueue(store.generation(initial.identity), initial)
        gate.prepared.await()
        val snapshots = (1..9).map { snapshot(snapshotIdentity("queued$it")) }
        val pending = snapshots.take(8).map { store.enqueue(store.generation(it.identity), it) }
        val rejected = store.enqueue(store.generation(snapshots[8].identity), snapshots[8])
        assertEquals(PiSnapshotWriteResult.QueueFull, rejected.await())
        val replacement = store.enqueue(store.generation(snapshots[0].identity), snapshots[0].copy(lastSeq = 99))
        assertEquals(PiSnapshotWriteResult.Superseded, pending[0].await())
        gate.release.complete(Unit)
        assertEquals(PiSnapshotWriteResult.Stored, first.await())
        assertEquals(PiSnapshotWriteResult.Stored, replacement.await())
        pending.drop(1).forEach { assertEquals(PiSnapshotWriteResult.Stored, it.await()) }
        assertEquals(8, directory.listFiles()!!.size)
        assertEquals(1, files.maxPreparations)
        assertNull(store.read(snapshots[8].identity))
        store.close()
    }

    @Test
    fun `delete invalidates queued inflight and later stale submissions before removing files`() = runTest {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler), files = files)
        val identity = snapshotIdentity()
        val generation = store.generation(identity)
        assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(generation, snapshot()).await())
        val gate = SnapshotWriteGate().also { files.gate = it }
        val inflight = store.enqueue(generation, snapshot(seq = 30))
        gate.prepared.await()
        val other = snapshot(snapshotIdentity("queued"))
        val queued = store.enqueue(store.generation(other.identity), other)
        store.delete(identity)
        store.delete(other.identity)
        assertEquals(PiSnapshotWriteResult.Invalidated, queued.await())
        assertEquals(PiSnapshotWriteResult.Invalidated, store.enqueue(generation, snapshot(seq = 40)).await())
        gate.release.complete(Unit)
        assertEquals(PiSnapshotWriteResult.Invalidated, inflight.await())
        assertNull(store.read(identity))
        assertNull(store.read(other.identity))
        assertTrue(directory.listFiles()!!.isEmpty())
        assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(store.generation(identity), snapshot(seq = 50)).await())
        assertEquals(50L, store.read(identity)?.lastSeq)
        store.close()
    }

    @Test
    fun `clear cannot be undone by queued or inflight writes`() = runTest {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler), files = files)
        val committed = snapshot(snapshotIdentity("committed"))
        assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(store.generation(committed.identity), committed).await())
        val gate = SnapshotWriteGate().also { files.gate = it }
        val first = snapshot()
        val inflight = store.enqueue(store.generation(first.identity), first)
        gate.prepared.await()
        val queuedSnapshot = snapshot(snapshotIdentity("queued"))
        val queued = store.enqueue(store.generation(queuedSnapshot.identity), queuedSnapshot)
        store.clear()
        gate.release.complete(Unit)
        assertEquals(PiSnapshotWriteResult.Invalidated, inflight.await())
        assertEquals(PiSnapshotWriteResult.Invalidated, queued.await())
        for (identity in listOf(first.identity, queuedSnapshot.identity, committed.identity)) assertNull(store.read(identity))
        assertTrue(directory.listFiles()!!.isEmpty())
        store.close()
    }

    @Test
    fun `generation invalidation retains committed files while rejecting unfinished writes`() = runTest {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler), files = files)
        val original = snapshot()
        val generation = store.generation(original.identity)
        assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(generation, original).await())
        val gate = SnapshotWriteGate().also { files.gate = it }
        val inflight = store.enqueue(generation, original.copy(lastSeq = 30))
        gate.prepared.await()
        val queued = store.enqueue(generation, original.copy(lastSeq = 40))
        store.invalidate()
        assertEquals(PiSnapshotWriteResult.Invalidated, queued.await())
        gate.release.complete(Unit)
        assertEquals(PiSnapshotWriteResult.Invalidated, inflight.await())
        assertEquals(original, store.read(original.identity))
        assertEquals(1, directory.listFiles()!!.size)
        store.close()
    }

    @Test
    fun `owner cancellation before worker starts still completes queued results`() = runTest {
        val directory = temporary.newFolder()
        val owner = CoroutineScope(backgroundScope.coroutineContext + Job(backgroundScope.coroutineContext[Job]))
        val store = PiSessionSnapshotStore(directory, owner, StandardTestDispatcher(testScheduler))
        val original = snapshot()
        val queued = store.enqueue(store.generation(original.identity), original)
        owner.cancel()
        runCurrent()
        assertEquals(PiSnapshotWriteResult.Invalidated, queued.await())
        assertTrue(directory.listFiles()!!.isEmpty())
        assertNull(store.read(original.identity))
        store.close()
    }

    @Test
    fun `generation cannot authorize another identity or another store`() = runTest {
        val directory = temporary.newFolder()
        val store = PiSessionSnapshotStore(directory, backgroundScope, StandardTestDispatcher(testScheduler))
        val original = snapshot()
        val token = store.generation(original.identity)
        assertEquals(PiSnapshotWriteResult.Invalidated, store.enqueue(token, snapshot(snapshotIdentity("other"))).await())
        val foreign = PiSnapshotGeneration(original.identity)
        assertEquals(PiSnapshotWriteResult.Invalidated, store.enqueue(foreign, original).await())
        runCurrent()
        assertTrue(directory.listFiles()!!.isEmpty())
        store.close()
    }

    @Test
    fun `cancelling store during temporary write preserves prior commit and completes pending results`() = runTest {
        val directory = temporary.newFolder()
        val files = ControlledPiSnapshotFiles(directory)
        val dispatcher = StandardTestDispatcher(testScheduler)
        val store = PiSessionSnapshotStore(directory, backgroundScope, dispatcher, files = files)
        val original = snapshot()
        val generation = store.generation(original.identity)
        assertEquals(PiSnapshotWriteResult.Stored, store.enqueue(generation, original).await())
        val gate = SnapshotWriteGate().also { files.gate = it }
        val inflight = store.enqueue(generation, original.copy(lastSeq = 30))
        gate.prepared.await()
        val queued = store.enqueue(generation, original.copy(lastSeq = 40))
        store.close()
        assertEquals(PiSnapshotWriteResult.Invalidated, inflight.await())
        assertEquals(PiSnapshotWriteResult.Invalidated, queued.await())
        assertEquals(0, files.activePreparations)
        assertEquals(1, directory.listFiles()!!.size)
        val reopened = PiSessionSnapshotStore(directory, backgroundScope, dispatcher)
        assertEquals(original, reopened.read(original.identity))
        reopened.close()
        runCurrent()
    }
}
