package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.PiSessionDto
import com.hpz.llmdockchat.data.model.PiState
import org.junit.Assert.assertEquals
import org.junit.Test

class PiSessionMapperTest {

    private fun dto(live: Boolean = true, state: String? = "idle") = PiSessionDto(
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
}
