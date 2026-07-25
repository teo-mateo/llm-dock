package com.hpz.llmdockchat.data.model

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * [ServiceSummary.isChatCapable] against the dashboard's own filter
 * (`dashboard/frontend/src/hooks/useRunningServices.js`): a recognised engine
 * prefix AND `(kind || 'chat') === 'chat'`. F07's brief called out checking
 * this rather than trusting F03's build of it — the blank-kind case here is
 * exactly the gap that check found: F03's `kind == "chat"` rejected a blank
 * `kind`, where the web treats it as `"chat"`.
 */
class ServiceSummaryTest {

    @Test
    fun `a running llamacpp service with an explicit chat kind is chat-capable`() {
        val service = ServiceSummary("llamacpp-a", "running", "chat")
        assertTrue(service.isChatCapable)
    }

    @Test
    fun `a blank kind is treated as chat, matching the web's (kind or chat) === chat`() {
        val service = ServiceSummary("vllm-a", "running", "")
        assertTrue(service.isChatCapable)
    }

    @Test
    fun `an embedding-kind service is never chat-capable, running or stopped`() {
        val runningEmbedding = ServiceSummary("vllm-bge-m3", "running", "embedding")
        val stoppedEmbedding = ServiceSummary("vllm-bge-m3", "not-created", "embedding")
        assertFalse(runningEmbedding.isChatCapable)
        assertFalse(stoppedEmbedding.isChatCapable)
    }

    @Test
    fun `open-webui is never chat-capable, even with kind chat, since its name has no engine prefix`() {
        val service = ServiceSummary("open-webui", "running", "chat")
        assertFalse(service.isChatCapable)
    }

    @Test
    fun `isRunning is only true for the running status, not exited or not-created`() {
        assertTrue(ServiceSummary("llamacpp-a", "running", "chat").isRunning)
        assertFalse(ServiceSummary("llamacpp-a", "exited", "chat").isRunning)
        assertFalse(ServiceSummary("llamacpp-a", "not-created", "chat").isRunning)
    }

    @Test
    fun `a stopped chat-capable service is still chat-capable, just not running`() {
        // Data-model level only: isChatCapable is a static property of the
        // service, independent of its current status. Since F07-RO, the
        // picker itself additionally requires isRunning before a local
        // service is shown at all — see ModelPickerSheetTest.
        val service = ServiceSummary("ds4-a", "exited", "chat")
        assertTrue(service.isChatCapable)
        assertFalse(service.isRunning)
    }
}
