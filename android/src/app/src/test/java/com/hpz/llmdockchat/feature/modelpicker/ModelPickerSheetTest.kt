package com.hpz.llmdockchat.feature.modelpicker

import com.hpz.llmdockchat.data.model.ServiceSummary
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * F07-RO (owner-requested deviation from F07-R2): the picker no longer has a
 * "Stopped" section, so [runningChatCapable] and [NOTHING_RUNNING_TEXT] are
 * pulled out of [ModelPickerSheet] to be testable without Compose — there is
 * no on-device way to see the empty state, since the dev rig always has at
 * least one chat-capable service running.
 */
class ModelPickerSheetTest {

    @Test
    fun `a stopped service never appears in the running list`() {
        val running = ServiceSummary("llamacpp-a", "running", "chat")
        val exited = ServiceSummary("llamacpp-b", "exited", "chat")
        val notCreated = ServiceSummary("llamacpp-c", "not-created", "chat")

        val result = runningChatCapable(listOf(running, exited, notCreated))

        assertEquals(listOf(running), result)
    }

    @Test
    fun `a non chat-capable running service never appears, even though it is running`() {
        val embedding = ServiceSummary("vllm-bge-m3", "running", "embedding")
        val openWebui = ServiceSummary("open-webui", "running", "chat")

        val result = runningChatCapable(listOf(embedding, openWebui))

        assertTrue(result.isEmpty())
    }

    @Test
    fun `running favourites sort first, ties otherwise kept in server order`() {
        val a = ServiceSummary("llamacpp-a", "running", "chat", favorite = false)
        val b = ServiceSummary("llamacpp-b", "running", "chat", favorite = true)
        val c = ServiceSummary("llamacpp-c", "running", "chat", favorite = false)

        val result = runningChatCapable(listOf(a, b, c))

        assertEquals(listOf(b, a, c), result)
    }

    @Test
    fun `the empty-state text matches the owner's wording exactly`() {
        assertEquals("No LLM-Dock models are running at this time.", NOTHING_RUNNING_TEXT)
    }
}
