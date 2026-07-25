package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.ActiveRunDto
import com.hpz.llmdockchat.data.dto.ConversationDto
import com.hpz.llmdockchat.data.model.Engine
import com.hpz.llmdockchat.data.model.ModelRef
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The wire↔domain seam for conversation rows (Architecture D6). The two
 * cases F02-R3 is most likely to get wrong: a null `active_run`, and one
 * carrying a terminal status — both must map to "not generating".
 */
class ConversationMapperTest {

    private fun dto(mainService: String = "llamacpp-laguna-s-2.1-q4", activeRun: ActiveRunDto? = null) =
        ConversationDto(
            id = "c1",
            title = "Speculative decoding on Laguna",
            mainService = mainService,
            updatedAt = "2026-07-25T10:00:00Z",
            activeRun = activeRun,
        )

    @Test
    fun `a null active_run maps to not generating`() {
        val summary = dto(activeRun = null).toDomain()
        assertNull(summary.activeRun)
        assertFalse(summary.isGenerating)
    }

    @Test
    fun `a running active_run maps to generating`() {
        val summary = dto(
            activeRun = ActiveRunDto(id = "r1", status = "running", activeStep = "Thinking…", startedAt = "2026-07-25T09:59:00Z"),
        ).toDomain()
        assertTrue(summary.isGenerating)
        assertEquals("r1", summary.activeRun?.id)
        assertEquals("Thinking…", summary.activeRun?.activeStep)
    }

    @Test
    fun `a queued active_run maps to generating`() {
        val summary = dto(activeRun = ActiveRunDto(id = "r1", status = "queued")).toDomain()
        assertTrue(summary.isGenerating)
    }

    @Test
    fun `a terminal-status run — however it got here — does not read as generating`() {
        for (status in listOf("completed", "failed", "cancelled")) {
            val summary = dto(activeRun = ActiveRunDto(id = "r1", status = status)).toDomain()
            assertFalse("status=$status should not be generating", summary.isGenerating)
        }
    }

    @Test
    fun `a dead service still maps, unrecognised rather than crashing`() {
        val summary = dto(mainService = "decommissioned-rig-3").toDomain()
        assertEquals(Engine.UNKNOWN, summary.engine)
        assertEquals("decommissioned-rig-3", (summary.modelRef as ModelRef.Local).serviceName)
    }

    @Test
    fun `an openrouter main_service maps to an OpenRouter ref`() {
        val summary = dto(mainService = "openrouter:anthropic/claude-sonnet-5").toDomain()
        assertEquals(Engine.OPEN_ROUTER, summary.engine)
        assertEquals("anthropic/claude-sonnet-5", (summary.modelRef as ModelRef.OpenRouter).modelId)
    }
}
