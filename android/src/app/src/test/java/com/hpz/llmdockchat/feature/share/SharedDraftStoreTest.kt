package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.prefs.DraftStore
import com.hpz.llmdockchat.testing.FakeDraftStore
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test
import java.io.IOException
import java.nio.file.Files
import java.util.concurrent.CountDownLatch
import kotlinx.coroutines.withTimeout

/**
 * The staged-share store: pending lifecycle, per-conversation attachment
 * records, and the reassign/remove/clear semantics behind the force-stop
 * and no-ghost rules — including what a pick leaves behind in a thread that
 * already holds unsent content (issue 270).
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

    private fun reassign(id: String, drafts: DraftStore = FakeDraftStore()) =
        runBlocking { store.reassign(id, drafts) }

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
        reassign("conv-1")
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

        reassign("conv-1", drafts)

        assertEquals("shared text", drafts.saved["conv-1"])
        assertEquals(listOf("data:image/jpeg;base64,AAA"), attachments("conv-1"))
        assertNull(store.pending.value)
    }

    @Test
    fun `reassign with no pending share is a no-op`() {
        val drafts = FakeDraftStore()
        reassign("conv-1", drafts)
        assertFalse(drafts.saved.containsKey("conv-1"))
    }

    @Test
    fun `reassign does not write a blank text into the draft store`() {
        store.stage(StagedShare(attachments = listOf("data:image/jpeg;base64,AAA")))
        val drafts = FakeDraftStore()

        reassign("conv-1", drafts)

        assertFalse(drafts.saved.containsKey("conv-1"))
        assertEquals(listOf("data:image/jpeg;base64,AAA"), attachments("conv-1"))
    }

    // -- reassign into a thread that already holds unsent content (issue 270) --

    /**
     * The loss this feature existed to stop: a question typed into a thread, and a
     * link shared into the same thread a minute later, which used to overwrite it.
     */
    @Test
    fun `a share into a thread with an unsent draft keeps the draft`() {
        store.stage(StagedShare(text = "SHARED_LINK https://example.com"))
        val drafts = FakeDraftStore(mapOf("conv-1" to "MY UNSENT QUESTION"))

        reassign("conv-1", drafts)

        assertEquals("MY UNSENT QUESTION\n\nSHARED_LINK https://example.com", drafts.saved["conv-1"])
        assertNull(store.pending.value)
    }

    @Test
    fun `a second share into the same thread keeps the first one's text too`() {
        val drafts = FakeDraftStore()
        store.stage(StagedShare(text = "FIRST_SHARE"))
        reassign("conv-1", drafts)
        store.stage(StagedShare(text = "SECOND_SHARE"))

        reassign("conv-1", drafts)

        assertEquals("FIRST_SHARE\n\nSECOND_SHARE", drafts.saved["conv-1"])
    }

    /**
     * Redelivery is the one duplicate worth refusing: the text is already the tail
     * of the composer, and a second copy is the noise this merge risks. The share
     * is still consumed, so the picker does not sit on it.
     */
    @Test
    fun `a redelivered share does not duplicate the text it already appended`() {
        store.stage(StagedShare(text = "SHARED_TEXT"))
        val drafts = FakeDraftStore(mapOf("conv-1" to "QUESTION\n\nSHARED_TEXT"))

        reassign("conv-1", drafts)

        assertEquals("QUESTION\n\nSHARED_TEXT", drafts.saved["conv-1"])
        assertNull(store.pending.value)
    }

    @Test
    fun `a whitespace-only draft is not kept ahead of the shared text`() {
        store.stage(StagedShare(text = "SHARED_TEXT"))
        val drafts = FakeDraftStore(mapOf("conv-1" to "   \n"))

        reassign("conv-1", drafts)

        assertEquals("SHARED_TEXT", drafts.saved["conv-1"])
    }

    @Test
    fun `a share of nothing leaves an existing draft exactly as it was`() {
        store.stage(StagedShare(attachments = listOf("data:image/jpeg;base64,AAA")))
        val drafts = FakeDraftStore(mapOf("conv-1" to "MY UNSENT QUESTION"))

        reassign("conv-1", drafts)

        assertEquals("MY UNSENT QUESTION", drafts.saved["conv-1"])
    }

    @Test
    fun `a share keeps the attachments an earlier share staged, and in order`() {
        runBlocking { store.appendAttachments("conv-1", listOf("data:image/jpeg;base64,EARLIER")) }
        store.stage(StagedShare(text = "caption", attachments = listOf("data:image/jpeg;base64,NEWER")))

        reassign("conv-1", FakeDraftStore())

        assertEquals(
            listOf("data:image/jpeg;base64,EARLIER", "data:image/jpeg;base64,NEWER"),
            attachments("conv-1"),
        )
    }

    /**
     * The pending record is what makes a lost share recoverable — it is on the
     * picker until the destination holds the content. Spending it first would turn
     * a failed write into silent data loss: text gone from the picker, and not in
     * the thread either.
     */
    @Test
    fun `a failed draft write leaves the share on the picker`() {
        store.stage(StagedShare(text = "SHARED_TEXT"))
        val drafts = FakeDraftStore()
        drafts.failOnSave = true

        assertTrue(reassign("conv-1", drafts).isFailure)

        assertEquals("SHARED_TEXT", store.pending.value?.text)
        assertEquals("SHARED_TEXT", SharedDraftStore(dir).pending.value?.text)
    }

    @Test
    fun `a failed attachment write leaves the share on the picker and writes nothing`() {
        store.stage(
            StagedShare(text = "SHARED_TEXT", attachments = listOf("data:image/jpeg;base64,AAA")),
        )
        val drafts = FakeDraftStore()
        java.io.File(dir, "conv_conv-1").writeText("not a directory")

        assertTrue(reassign("conv-1", drafts).isFailure)

        assertEquals("SHARED_TEXT", store.pending.value?.text)
        assertEquals("SHARED_TEXT", SharedDraftStore(dir).pending.value?.text)
        assertTrue(
            "a failed append must not leave a partial record",
            runBlocking { store.attachments("conv-1") }.isEmpty(),
        )
    }

    @Test
    fun `a retried pick adds one copy of the text and one of each attachment`() {
        store.stage(
            StagedShare(
                text = "SHARED_TEXT",
                attachments = listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB"),
            ),
        )
        val drafts = FakeDraftStore()
        val blocker = java.io.File(dir, "conv_conv-1").apply { writeText("not a directory") }

        assertTrue("the first attempt fails", reassign("conv-1", drafts).isFailure)
        assertTrue(blocker.delete())
        assertTrue("the retry succeeds", reassign("conv-1", drafts).isSuccess)

        assertEquals("the text is not duplicated", "SHARED_TEXT", drafts.saved["conv-1"])
        assertEquals(
            listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB"),
            runBlocking { store.attachments("conv-1") },
        )
        assertNull(store.pending.value)
    }

    /**
     * The writes landed but the caller went away before the spend. The spend
     * must still happen: the attachments are on disk, and a re-pick would
     * append them a second time.
     */
    @Test
    fun `a cancelled pick still spends the record, so a re-pick writes nothing twice`() {
        store.stage(
            StagedShare(text = "shared", attachments = listOf("data:image/jpeg;base64,AAA")),
        )
        val drafts = FakeDraftStore()
        val started = kotlinx.coroutines.CompletableDeferred<Unit>()
        val gate = kotlinx.coroutines.CompletableDeferred<Unit>()
        val gated = object : DraftStore by drafts {
            override suspend fun saveConfirmed(conversationId: String, text: String): Result<Unit> {
                started.complete(Unit)
                gate.await()
                return drafts.saveConfirmed(conversationId, text)
            }
        }

        runBlocking {
            val job = launch(kotlinx.coroutines.Dispatchers.Default) { store.reassign("conv-1", gated) }
            started.await()
            job.cancel()
            gate.complete(Unit)
            job.join()
        }

        assertNull("the record must be spent even though the caller was cancelled", store.pending.value)
        assertEquals(listOf("data:image/jpeg;base64,AAA"), attachments("conv-1"))

        assertTrue(reassign("conv-1", drafts).isSuccess)
        assertEquals(
            "a re-pick must not append the attachments again",
            listOf("data:image/jpeg;base64,AAA"),
            attachments("conv-1"),
        )
    }

    @Test
    fun `a share staged during a pick survives it`() {
        store.stage(StagedShare(text = "first"))
        val drafts = FakeDraftStore()
        val restaging = object : DraftStore by drafts {
            override suspend fun saveConfirmed(conversationId: String, text: String): Result<Unit> {
                store.stage(StagedShare(text = "second"))
                return drafts.saveConfirmed(conversationId, text)
            }
        }

        assertTrue(reassign("conv-1", restaging).isSuccess)

        assertEquals("the pick filed the one it captured", "first", drafts.saved["conv-1"])
        assertEquals("the newer share is still staged", "second", store.pending.value?.text)
    }

    /**
     * Durability, not just call order. The record outlives the destination
     * writes: at the moment the first one starts, `pending.json` is still there
     * to re-offer the share, and only a confirmed write of both halves spends it.
     */
    @Test
    fun `a pick puts the attachments on disk before it spends the record`() {
        val other = Files.createTempDirectory("durable-pick").toFile()
        var recordSeenAtTheFirstWrite: Boolean? = null
        val scope = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO)
        try {
            val queued = SharedDraftStore(other, scope)
            queued.stage(StagedShare(text = "shared", attachments = listOf("data:image/jpeg;base64,AAA")))

            val result = runBlocking {
                withTimeout(5_000) {
                    queued.reassign(
                        "conv-1",
                        ObservingDraftStore {
                            recordSeenAtTheFirstWrite = java.io.File(other, "pending.json").exists()
                        },
                    )
                }
            }

            assertTrue("the pick must succeed", result.isSuccess)
            assertEquals(
                "the record must outlive the destination write",
                true,
                recordSeenAtTheFirstWrite,
            )
            assertNull(SharedDraftStore(other).pending.value)
            assertEquals(
                listOf("data:image/jpeg;base64,AAA"),
                runBlocking { SharedDraftStore(other).attachments("conv-1") },
            )
        } finally {
            scope.cancel()
        }
    }

    /** Runs [onConfirmed] at the pick's first destination write, where a test can read the disk. */
    private class ObservingDraftStore(private val onConfirmed: () -> Unit) : DraftStore {
        private val saved = mutableMapOf<String, String>()
        override suspend fun draft(conversationId: String): String = saved[conversationId].orEmpty()
        override fun save(conversationId: String, text: String) { saved[conversationId] = text }
        override fun clear(conversationId: String) { saved.remove(conversationId) }
        override suspend fun saveConfirmed(conversationId: String, text: String): Result<Unit> {
            saved[conversationId] = text
            onConfirmed()
            return Result.success(Unit)
        }
    }

    // -- the merge rule itself ---------------------------------------------

    @Test
    fun `mergedDraft puts the draft first and separates it from the share`() {
        assertEquals("draft\n\nshare", mergedDraft("draft", "share"))
    }

    @Test
    fun `mergedDraft keeps a one-sided input unchanged`() {
        assertEquals("share", mergedDraft("", "share"))
        assertEquals("share", mergedDraft("  \n ", "share"))
        assertEquals("draft", mergedDraft("draft", ""))
        assertEquals("draft", mergedDraft("draft", "   "))
    }

    @Test
    fun `mergedDraft trims the shared text's trailing whitespace but keeps its own breaks`() {
        assertEquals(
            "draft\n\nline one\nline two",
            mergedDraft("draft", "line one\nline two\n\n"),
        )
    }

    @Test
    fun `mergedDraft refuses only an exact tail match`() {
        assertEquals("a\n\nb", mergedDraft("a\n\nb", "b"))
        assertEquals("a\n\nb\n\nb (2)", mergedDraft("a\n\nb", "b (2)"))
    }

    // -- per-conversation records -------------------------------------------

    @Test
    fun `attachments survive a store rebuild - the force-stop case`() {
        runBlocking { store.appendAttachments("conv-1", listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB")) }
        val reborn = SharedDraftStore(dir)
        assertEquals(listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB"), runBlocking { reborn.attachments("conv-1") })
    }

    @Test
    fun `records are keyed per conversation`() {
        runBlocking { store.appendAttachments("conv-1", listOf("data:image/jpeg;base64,AAA")) }
        runBlocking { store.appendAttachments("conv-2", listOf("data:image/jpeg;base64,BBB")) }
        assertEquals(listOf("data:image/jpeg;base64,AAA"), attachments("conv-1"))
        assertEquals(listOf("data:image/jpeg;base64,BBB"), attachments("conv-2"))
    }

    @Test
    fun `removeAttachment deletes that index and renumbers the rest`() {
        runBlocking { store.appendAttachments("conv-1", listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB")) }
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
        runBlocking { store.appendAttachments("conv-1", listOf("data:image/jpeg;base64,AAA")) }
        store.clear("conv-1")
        assertTrue(attachments("conv-1").isEmpty())
        // And a rebuild does not resurrect it.
        assertTrue(runBlocking { SharedDraftStore(dir).attachments("conv-1") }.isEmpty())
    }

    @Test
    fun `a second attachment write appends rather than replacing the record`() {
        runBlocking { store.appendAttachments("conv-1", listOf("data:image/jpeg;base64,AAA")) }
        runBlocking { store.appendAttachments("conv-1", listOf("data:image/jpeg;base64,BBB")) }
        assertEquals(listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB"), attachments("conv-1"))
    }

    @Test
    fun `a removed attachment keeps the merged record index-aligned`() {
        runBlocking { store.appendAttachments("conv-1", listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,BBB")) }
        runBlocking { store.appendAttachments("conv-1", listOf("data:image/jpeg;base64,CCC")) }
        store.removeAttachment("conv-1", 1)

        assertEquals(listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,CCC"), attachments("conv-1"))

        runBlocking { store.appendAttachments("conv-1", listOf("data:image/jpeg;base64,DDD")) }
        assertEquals(
            listOf("data:image/jpeg;base64,AAA", "data:image/jpeg;base64,CCC", "data:image/jpeg;base64,DDD"),
            attachments("conv-1"),
        )
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
            runBlocking { queued.appendAttachments("conv-1", listOf("data:image/jpeg;base64,AAA")) }

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

        reassign("conv-1")

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
