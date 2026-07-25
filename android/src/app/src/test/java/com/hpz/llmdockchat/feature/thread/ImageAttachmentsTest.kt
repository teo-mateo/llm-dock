package com.hpz.llmdockchat.feature.thread

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The pure half of F04-R9's downscaling. The decode itself needs a device;
 * picking the sample size does not, and it is the part that decides whether a
 * 12-megapixel photo is ever fully materialised in memory.
 */
class ImageAttachmentsTest {

    @Test
    fun `an image already within the cap is decoded at full size`() {
        assertEquals(1, sampleSizeFor(1024, 768, MAX_ATTACHMENT_EDGE_PX))
        assertEquals(1, sampleSizeFor(MAX_ATTACHMENT_EDGE_PX, 1000, MAX_ATTACHMENT_EDGE_PX))
    }

    @Test
    fun `a phone-camera photo is halved until it is near the cap, never below it`() {
        // 4032x3024 — a 12 MP phone photo. 4032/2 = 2016 is still over 1568;
        // 4032/4 = 1008 would be under, so 2 is the largest safe step.
        assertEquals(2, sampleSizeFor(4032, 3024, MAX_ATTACHMENT_EDGE_PX))
        assertEquals(4, sampleSizeFor(8000, 6000, MAX_ATTACHMENT_EDGE_PX))
    }

    @Test
    fun `orientation does not matter — the long edge decides`() {
        assertEquals(
            sampleSizeFor(4032, 3024, MAX_ATTACHMENT_EDGE_PX),
            sampleSizeFor(3024, 4032, MAX_ATTACHMENT_EDGE_PX),
        )
    }

    @Test
    fun `a degenerate size never returns an invalid sample size`() {
        assertEquals(1, sampleSizeFor(0, 0, MAX_ATTACHMENT_EDGE_PX))
    }
}
