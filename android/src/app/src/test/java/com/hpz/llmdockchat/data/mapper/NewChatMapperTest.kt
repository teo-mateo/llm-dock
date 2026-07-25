package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.ServiceDto
import com.hpz.llmdockchat.data.model.ServiceSummary
import org.junit.Assert.assertEquals
import org.junit.Test

/** [ServiceDto.toDomain] — F07 added `host_port`/`favorite` on top of F03's `name`/`status`/`kind`. */
class NewChatMapperTest {

    @Test
    fun `host_port and favorite map straight through, and api_key has no field to map from`() {
        val dto = ServiceDto(
            name = "llamacpp-a",
            status = "running",
            kind = "chat",
            hostPort = 3301,
            favorite = true,
        )
        assertEquals(
            ServiceSummary(name = "llamacpp-a", status = "running", kind = "chat", port = 3301, favorite = true),
            dto.toDomain(),
        )
    }

    @Test
    fun `defaults are zero and false when the server omits the fields`() {
        val dto = ServiceDto(name = "llamacpp-a", status = "running", kind = "chat")
        val summary = dto.toDomain()
        assertEquals(0, summary.port)
        assertEquals(false, summary.favorite)
    }
}
