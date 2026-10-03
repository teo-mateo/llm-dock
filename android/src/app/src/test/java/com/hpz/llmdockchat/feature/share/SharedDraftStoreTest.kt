package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.testing.FakeDraftStore
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
}
