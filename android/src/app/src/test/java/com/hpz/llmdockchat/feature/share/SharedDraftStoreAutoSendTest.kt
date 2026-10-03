package com.hpz.llmdockchat.feature.share

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.nio.file.Files

/**
 * The summarize claim: durable, spent by one read, and filed where an
 * attachment write cannot reach it — the three things that make "at most one
 * turn per summarize" true across process death.
 */
class SharedDraftStoreAutoSendTest {

    private lateinit var dir: java.io.File
    private lateinit var store: SharedDraftStore

    @Before
    fun setUp() {
        dir = Files.createTempDirectory("shared-drafts").toFile()
        store = SharedDraftStore(dir)
    }

    private fun take(id: String = CONV) = runBlocking { store.takeAutoSend(id) }

    @Test
    fun `filing a claim spends the pending share in the same call`() {
        store.stage(StagedShare(text = "https://example.com/a", url = "https://example.com/a"))

        store.stageForAutoSend(CONV, "summarise it")

        assertNull(store.pending.value)
        assertEquals("summarise it", take())
    }

    @Test
    fun `a claim is owed once - the second read finds nothing`() {
        store.stageForAutoSend(CONV, "summarise it")

        assertEquals("summarise it", take())
        assertNull(take())
    }

    /** Process-death: the intent outlives the store object. */
    @Test
    fun `a claim survives process death and is still owed exactly once`() {
        store.stageForAutoSend(CONV, "summarise it")

        val reborn = SharedDraftStore(dir)

        assertEquals("summarise it", runBlocking { reborn.takeAutoSend(CONV) })
        assertNull(runBlocking { SharedDraftStore(dir).takeAutoSend(CONV) })
    }

    /** The claim is a sibling of the attachment dir, which `saveAttachments` wipes. */
    @Test
    fun `an attachment write after the claim does not erase it`() {
        store.stageForAutoSend(CONV, "summarise it")

        store.saveAttachments(CONV, listOf("data:image/jpeg;base64,AAA"))

        assertEquals("summarise it", take())
    }

    @Test
    fun `sending the thread clears the claim - no ghost turn on a later visit`() {
        store.stageForAutoSend(CONV, "summarise it")

        store.clear(CONV)

        assertNull(take())
    }

    @Test
    fun `a conversation with no claim takes nothing`() {
        assertNull(take())
        assertTrue(store.pending.value == null)
    }

    private companion object {
        const val CONV = "conv-1"
    }
}
