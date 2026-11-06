package com.hpz.llmdockchat.navigation

import com.hpz.llmdockchat.data.model.PiSessionKey
import org.junit.Assert.assertEquals
import org.junit.Test

class PiSessionDestinationTest {
    @Test
    fun `piSession encodes path segments`() {
        assertEquals(
            "pi/s%201%2Fa/i%3F2",
            Destinations.piSession(PiSessionKey("s 1/a", "i?2")),
        )
    }
}
