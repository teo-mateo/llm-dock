package com.hpz.llmdockchat.core.time

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant
import java.time.ZoneId
import java.util.Locale

class TimestampsTest {

    // UTC+3 in July, so a UTC wall clock rendered raw would be three hours off.
    private val bucharest = ZoneId.of("Europe/Bucharest")
    private val now = Instant.parse("2026-07-24T15:43:46Z")
    private val uk = Locale.UK

    private fun label(raw: String, zone: ZoneId = bucharest) =
        Timestamps.relative(raw, now, zone, uk)

    @Test
    fun `the last minute reads as just now`() {
        assertEquals("just now", label("2026-07-24T15:43:20Z"))
        assertEquals("just now", label("2026-07-24T15:43:46Z"))
    }

    @Test
    fun `earlier today reads as a local wall clock`() {
        assertEquals("18:32", label("2026-07-24T15:32:36Z"))
        assertEquals("16:32", label("2026-07-24T15:32:36Z", ZoneId.of("Europe/London")))
        assertEquals("11:32", label("2026-07-24T15:32:36Z", ZoneId.of("America/New_York")))
    }

    @Test
    fun `the local day boundary decides, not the UTC one`() {
        // 22:10 UTC on the 23rd is 01:10 on the 24th in Bucharest — today, there.
        assertEquals("01:10", label("2026-07-23T22:10:00Z"))
        assertEquals("yesterday", label("2026-07-23T22:10:00Z", ZoneId.of("Europe/London")))
    }

    @Test
    fun `yesterday is named`() {
        assertEquals("yesterday", label("2026-07-23T09:00:00Z"))
    }

    @Test
    fun `the past week is a weekday name`() {
        assertEquals("Tue", label("2026-07-21T09:00:00Z"))
        assertEquals("Sat", label("2026-07-18T09:00:00Z"))
    }

    @Test
    fun `older this year is a day and month`() {
        assertEquals("3 Mar", label("2026-03-03T09:00:00Z"))
    }

    @Test
    fun `a previous year carries the year`() {
        assertEquals("14 Nov 2025", label("2025-11-14T09:00:00Z"))
    }

    @Test
    fun `microseconds and a missing Z both parse as UTC`() {
        assertEquals("18:32", label("2026-07-24T15:32:36.029930Z"))
        assertEquals("18:32", label("2026-07-24T15:32:36"))
        assertEquals("18:32", label("2026-07-24T15:32:36+00:00"))
        assertEquals("21:32", label("2026-07-24T15:32:36-03:00"))
    }

    @Test
    fun `unparseable input is shown rather than blanked`() {
        assertEquals("never", label("never"))
        assertNull(Timestamps.parse("never"))
        assertNull(Timestamps.parse(""))
    }
}
