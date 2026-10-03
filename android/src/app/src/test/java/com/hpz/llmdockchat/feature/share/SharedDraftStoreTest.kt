package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.testing.FakeDraftStore
import kotlinx.coroutines.cancel
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.nio.file.Files

/**
 * The staged-share store: pending lifecycle, per-conversation attachment
 * records, and the reassign/remove/clear semantics behind the force-stop
 * and no-ghost rules.
 */
class SharedDraftStoreTest {

    private lateinit var store: SharedDraftStore
    private lateinit var dir: java.io.File

    @Before
    fun setUp() {
        dir = Files.createTempDirectory("shared-drafts").toFile()
        store = SharedDraftStore(dir)
    }

    private fun attachments(id: String) = runBlocking { store.attachments(id) }

    // -- pending ------------------------------------------------------------

    @Test
    fun `staging a share makes it the pending share`() {
        assertNull(store.pending.value)
        store.stage(StagedShare(text = "hello"))
        assertEquals("hello", store.pending.value?.text)
    }

    @Test
    fun `clearPending drops the pending share and the on-disk record`() {
        store.stage(StagedShare(text = "hello"))
        store.clearPending()
        assertNull(store.pending.value)
        // A fresh store hydrates from disk — the record must really be gone.
        assertNull(SharedDraftStore(dir).pending.value)
    }

    @Test
    fun `a new store hydrates a pending share from disk - process death during the picker`() {
        store.stage(StagedShare(text = "hello", error = null))
        val reborn = SharedDraftStore(dir)
        assertEquals("hello", reborn.pending.value?.text)
    }

    @Test
    fun `a staged share records its delivery token as handled`() {
        store.stage(StagedShare(text = "hello"), token = "tok-1")
        assertEquals("tok-1", store.handledToken)
        // Survives process death: a fresh store over the same dir agrees.
        assertEquals("tok-1", SharedDraftStore(dir).handledToken)
    }

    @Test
    fun `clearPending consumes the record and keeps the claim`() {
        store.stage(StagedShare(text = "hello"), token = "tok-1")
        store.clearPending()
        assertNull(store.pending.value)
        assertEquals("tok-1", store.handledToken)
        val reborn = SharedDraftStore(dir)
        assertNull(reborn.pending.value)
        assertEquals("tok-1", reborn.handledToken)
    }

    @Test
    fun `reassign keeps the claim`() {
        store.stage(StagedShare(text = "hello"), token = "tok-1")
        store.reassign("conv-1", FakeDraftStore())
        assertNull(store.pending.value)
        assertEquals("tok-1", store.handledToken)
        assertEquals("tok-1", SharedDraftStore(dir).handledToken)
    }

    @Test
    fun `a corrupt handled record reads as no claim`() {
        dir.mkdirs()
        store.stage(StagedShare(text = "hello"), token = "tok-1")
        java.io.File(dir, "handled.json").writeText("not json")
        val reborn = SharedDraftStore(dir)
        assertNull(reborn.handledToken)
        // Pending hydration is unaffected by the sibling's corruption.
        assertEquals("hello", reborn.pending.value?.text)
    }

    @Test
    fun `stage with no token leaves the claim alone`() {
        store.stage(StagedShare(text = "first"), token = "tok-1")
        store.stage(StagedShare(text = "second"))
        assertEquals("tok-1", store.handledToken)
        assertEquals("second", store.pending.value?.text)
        assertNull(SharedDraftStore(Files.createTempDirectory("shared-drafts-b").toFile()).handledToken)
    }

    // -- reassign -----------------------------------------------------------

    @Test
    fun `reassign moves text into the draft store and attachments into the conversation record`() {
        store.stage(StagedShare(text = "shared text", attachments = listOf("data:image/jpeg;base64,AAA")))
        val drafts = FakeDraftStore()

        store.reassign("conv-1", drafts)

        assertEquals("shared text", drafts.saved["conv-1"])
        assertEquals(listOf("data:image/jpeg;base64,AAA"), attachments("conv-1"))
        assertNull(store.pending.value)
    }

    @Test
    fun `reassign with no pending share is a no-op`() {
        val drafts = FakeDraftStore()
        store.reassign("conv-1", drafts)
        assertFalse(drafts.saved.containsKey("conv-1"))
    }

    @Test
    fun `reassign does not write a blank text into the draft store`() {
        store.stage(StagedShare(attachments = listOf("data:image/jpeg;base64,AAA")))
        val drafts = FakeDraftStore()

        store.reassign("conv-1", drafts)

        assertFalse(drafts.saved.containsKey("conv-1"))
        assertEquals(listOf("data:image/jpeg;base64,AAA"), attachments("conv-1"))
    }

    // -- per-conversation records -------------------------------------------

    @Test
    fun `attachments survive a store rebuild - the force-stop case`() {
        store.saveAttachments("conv-1", listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB"))
        val reborn = SharedDraftStore(dir)
        assertEquals(listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB"), runBlocking { reborn.attachments("conv-1") })
    }

    @Test
    fun `records are keyed per conversation`() {
        store.saveAttachments("conv-1", listOf("data:image/jpeg;base64,AAA"))
        store.saveAttachments("conv-2", listOf("data:image/jpeg;base64,BBB"))
        assertEquals(listOf("data:image/jpeg;base64,AAA"), attachments("conv-1"))
        assertEquals(listOf("data:image/jpeg;base64,BBB"), attachments("conv-2"))
    }

    @Test
    fun `removeAttachment deletes that index and renumbers the rest`() {
        store.saveAttachments("conv-1", listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB"))
        store.removeAttachment("conv-1", 0)
        assertEquals(listOf("data:image/jpeg;base64,BBB"), attachments("conv-1"))
    }

    @Test
    fun `removeAttachment on an empty record is a no-op`() {
        store.removeAttachment("conv-1", 0)
        assertTrue(attachments("conv-1").isEmpty())
    }

    @Test
    fun `clear deletes the conversation record - send or leave`() {
        store.saveAttachments("conv-1", listOf("data:image/jpeg;base64,AAA"))
        store.clear("conv-1")
        assertTrue(attachments("conv-1").isEmpty())
        // And a rebuild does not resurrect it.
        assertTrue(runBlocking { SharedDraftStore(dir).attachments("conv-1") }.isEmpty())
    }

    @Test
    fun `saveAttachments replaces the previous record`() {
        store.saveAttachments("conv-1", listOf("data:image/jpeg;base64,AAA"))
        store.saveAttachments("conv-1", listOf("data:image/jpeg;base64,BBB"))
        assertEquals(listOf("data:image/jpeg;base64,BBB"), attachments("conv-1"))
    }

    @Test
    fun `a corrupt pending record hydrates as null rather than crashing`() {
        dir.mkdirs()
        java.io.File(dir, "pending.json").writeText("not json")
        assertNull(SharedDraftStore(dir).pending.value)
    }

    /**
     * The hazard the queue exists for: a dismissal followed immediately by a new
     * share must not leave the dismissed one on disk. Writes land on another
     * thread, so this only holds if they are applied in call order.
     */
    @Test
    fun `writes made on the io scope reach disk in call order`() {
        val other = Files.createTempDirectory("queued-drafts").toFile()
        val scope = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO)
        try {
            val queued = SharedDraftStore(other, scope)
            queued.stage(StagedShare(text = "first"))
            queued.clearPending()
            queued.stage(StagedShare(text = "second"))
            runBlocking { queued.awaitPendingWrites() }

            assertEquals("second", SharedDraftStore(other).pending.value?.text)
        } finally {
            scope.cancel()
        }
    }

    /**
     * Picking a target writes the attachments and then opens the thread, which
     * reads them back a moment later. The read must answer for the write it
     * follows, not for whatever was on disk when it started.
     */
    @Test
    fun `attachments written on the io scope are readable as soon as they are asked for`() {
        val other = Files.createTempDirectory("queued-attachments").toFile()
        val scope = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO)
        try {
            val queued = SharedDraftStore(other, scope)
            queued.saveAttachments("conv-1", listOf("data:image/jpeg;base64,AAA"))

            assertEquals(
                listOf("data:image/jpeg;base64,AAA"),
                runBlocking { queued.attachments("conv-1") },
            )
        } finally {
            scope.cancel()
        }
    }

    /**
     * The picker's Close button and the import run on different threads, so the
     * dismissal has to win whichever of them touches the record last — otherwise a
     * share the user threw away comes back after a restart. The window is a real
     * interleaving, so this is a race run many times: an iteration that misses the
     * window proves nothing, and one that lands cannot pass by luck.
     */
    @Test
    fun `a dismissal racing the import never comes back`() = runBlocking {
        repeat(200) { round ->
            store.beginImport("tok")
            val go = java.util.concurrent.CountDownLatch(1)
            val importing = Thread {
                go.await()
                store.finishImport("tok", StagedShare(text = "arrived late"))
            }
            val dismissing = Thread {
                go.await()
                store.clearPending()
            }
            importing.start()
            dismissing.start()
            go.countDown()
            importing.join()
            dismissing.join()
            store.awaitPendingWrites()

            assertNull("round $round resurrected a dismissed share", store.pending.value)
            assertNull("round $round wrote a dismissed share", SharedDraftStore(dir).pending.value)
        }
    }

    @Test
    fun `a placeholder is not content the picker can spend`() {
        store.beginImport("tok")

        store.reassign("conv-1", FakeDraftStore())

        assertEquals("the incoming bytes still own the record", true, store.pending.value?.importing)
    }

    /**
     * A drain that throws has to report: the caller is a screen sitting on Loading,
     * and a deferred that never completes turns an I/O error into a permanent wait.
     */
    @Test
    fun `a failing attachment read surfaces instead of hanging`() {
        java.io.File(dir, "conv_conv-1").mkdirs()
        java.io.File(dir, "conv_conv-1/0.txt").mkdir()

        val failure = runCatching {
            runBlocking { kotlinx.coroutines.withTimeout(5_000) { store.attachments("conv-1") } }
        }.exceptionOrNull()

        assertTrue("expected the read to fail, got: $failure", failure is java.io.IOException)
    }
}
