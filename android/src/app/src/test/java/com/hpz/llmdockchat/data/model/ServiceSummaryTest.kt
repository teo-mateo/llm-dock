package com.hpz.llmdockchat.data.model

import com.hpz.llmdockchat.data.dto.ServiceDto
import com.hpz.llmdockchat.data.mapper.toDomain
import org.junit.Assert.assertEquals
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

    @Test
    fun `a sglang service is chat-capable — the prefix table knows it, unlike an unrecognised name`() {
        val service = ServiceSummary("sglang-qwen3-8-flash-next-mixed-nvfp4-fp8", "running", "chat")
        assertEquals(Engine.SGLANG, service.engine)
        assertTrue(service.isChatCapable)
    }

    @Test
    fun `ik, exl3 and ninfer services are chat-capable — the #269 gap, closed`() {
        // Each of these evaluated false on the 415c0cc baseline (unknown engine),
        // so their Models rows omitted New chat and they were filtered out of
        // every picker.
        for ((name, engine) in listOf(
            "ik-qwen3.6-27b-iq4xs" to Engine.IK_LLAMA_CPP,
            "exl3-gemma-4-31b-it" to Engine.TABBYAPI,
            "ninfer-qwen3.8-27b-nvfp4" to Engine.NINFER,
        )) {
            val service = ServiceSummary(name, "running", "chat")
            assertEquals(engine, service.engine)
            assertTrue("$name should be chat-capable", service.isChatCapable)
        }
    }

    @Test
    fun `template_type is authoritative over the name prefix, and null falls back to it`() {
        // The engine that selected the compose template beats a display name a
        // rename could have changed.
        assertEquals(Engine.NINFER, ServiceSummary("vllm-misnamed", "running", "chat", templateType = "ninfer").engine)
        // A name with no recognised prefix still classifies off template_type.
        assertEquals(Engine.TABBYAPI, ServiceSummary("legacy-service", "running", "chat", templateType = "tabbyapi").engine)
        assertTrue(ServiceSummary("legacy-service", "running", "chat", templateType = "tabbyapi").isChatCapable)
        // An older snapshot with no template_type still resolves by prefix.
        assertEquals(Engine.IK_LLAMA_CPP, ServiceSummary("ik-a", "running", "chat", templateType = null).engine)
        // A template_type naming an unknown engine falls back to the prefix rather
        // than masking it.
        assertEquals(Engine.VLLM, ServiceSummary("vllm-a", "running", "chat", templateType = "mystery-engine").engine)
    }

    @Test
    fun `engineFromTemplateType maps every engine and nulls an unknown one`() {
        assertEquals(Engine.VLLM, engineFromTemplateType("vllm"))
        assertEquals(Engine.LLAMA_CPP, engineFromTemplateType("llamacpp"))
        assertEquals(Engine.IK_LLAMA_CPP, engineFromTemplateType("ik_llamacpp"))
        assertEquals(Engine.DS4, engineFromTemplateType("ds4"))
        assertEquals(Engine.TABBYAPI, engineFromTemplateType("tabbyapi"))
        assertEquals(Engine.NINFER, engineFromTemplateType("ninfer"))
        assertEquals(Engine.SGLANG, engineFromTemplateType("sglang"))
        assertEquals(null, engineFromTemplateType("something-new"))
        assertEquals(null, engineFromTemplateType(null))
    }

    /**
     * F15-R8's proof for the 90 % of services that declare no ladder: the new
     * field defaults to empty, so a row that predates F15 is still equal to
     * itself. Every pre-F15 assertion in this suite stays green unchanged.
     */
    @Test
    fun `a row with no reasoning_levels maps to exactly the pre-F15 summary`() {
        val row = ServiceDto(name = "llamacpp-a", status = "running", kind = "chat", hostPort = 3301)
        assertEquals(
            ServiceSummary(name = "llamacpp-a", status = "running", kind = "chat", port = 3301),
            row.toDomain(),
        )
        assertEquals(emptyList<String>(), row.toDomain().reasoningLevels)
    }
}
