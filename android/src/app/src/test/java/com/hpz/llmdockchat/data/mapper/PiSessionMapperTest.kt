package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.PiPromptDto
import com.hpz.llmdockchat.data.dto.PiSessionDto
import com.hpz.llmdockchat.data.model.PiState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PiSessionMapperTest {

    private fun dto(
        live: Boolean = true,
        state: String? = "idle",
        prompts: List<PiPromptDto> = emptyList(),
    ) = PiSessionDto(
        sessionId = "s1",
        instanceId = "i1",
        name = "llm-dock",
        cwd = "/repo",
        model = "mistral/small",
        thinkingLevel = "high",
        firstSeen = 1000,
        lastSeen = 2000,
        endedAt = null,
        endReason = null,
        live = live,
        state = state,
        contextPercent = 22.5,
        prompts = prompts,
    )

    @Test
    fun `ended when not live`() {
        assertEquals(PiState.ENDED, dto(live = false, state = "working").toDomain().state)
    }

    @Test
    fun `working from state`() {
        assertEquals(PiState.WORKING, dto(live = true, state = "working").toDomain().state)
    }

    @Test
    fun `unknown state maps to idle`() {
        assertEquals(PiState.IDLE, dto(live = true, state = "something-else").toDomain().state)
        assertEquals(PiState.IDLE, dto(live = true, state = null).toDomain().state)
    }

    @Test
    fun `no open prompts maps to an empty list and no answer needed`() {
        val session = dto().toDomain()
        assertEquals(emptyList<Any>(), session.prompts)
        assertFalse(session.needsAnswer)
    }

    @Test
    fun `open prompts map through and need an answer`() {
        val session = dto(
            prompts = listOf(
                PiPromptDto(promptId = "p1", kind = "approval", title = "Approve rm?"),
                PiPromptDto(promptId = "p2", kind = "select", title = null),
            ),
        ).toDomain()

        assertEquals(2, session.prompts.size)
        assertEquals("p1", session.prompts[0].promptId)
        assertEquals("approval", session.prompts[0].kind)
        assertEquals("Approve rm?", session.prompts[0].title)
        assertNull(session.prompts[1].title)
        assertTrue(session.needsAnswer)
    }

    @Test
    fun `a stored prompt on an ended session needs no answer`() {
        val session = dto(
            live = false,
            state = null,
            prompts = listOf(PiPromptDto(promptId = "p1", kind = "confirm", title = "Run it?")),
        ).toDomain()

        assertEquals(1, session.prompts.size)
        assertFalse(session.needsAnswer)
    }
}
