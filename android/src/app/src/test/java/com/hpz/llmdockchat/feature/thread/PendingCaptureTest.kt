package com.hpz.llmdockchat.feature.thread

import androidx.compose.runtime.saveable.SaverScope
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The capture survives the process being reclaimed while the camera is open, so
 * what it means once the result arrives is decided here rather than in a
 * composable that no unit test can recreate.
 */
class PendingCaptureTest {

    private val scope = SaverScope { true }

    private fun roundTrip(value: PendingCapture): PendingCapture {
        val saved = with(PendingCapture.Saver) { scope.save(value) }
        return PendingCapture.Saver.restore(saved!!)!!
    }

    @Test
    fun `the destination and the in-flight capture both survive the saver`() {
        val restored = roundTrip(PendingCapture(destination = "content://a", inFlight = "content://b"))
        assertEquals("content://a", restored.destination)
        assertEquals("content://b", restored.inFlight)
    }

    @Test
    fun `an empty value survives the saver as empty`() {
        val restored = roundTrip(PendingCapture())
        assertNull(restored.destination)
        assertNull(restored.inFlight)
    }

    @Test
    fun `a saved result imports the destination`() {
        val outcome = PendingCapture(destination = "content://a").consume(saved = true)
        assertEquals(CaptureOutcome.Import("content://a"), outcome)
    }

    @Test
    fun `a cancelled result discards the destination`() {
        val outcome = PendingCapture(destination = "content://a").consume(saved = false)
        assertEquals(CaptureOutcome.Discard("content://a"), outcome)
    }

    @Test
    fun `a result with no destination is unrecoverable rather than silent`() {
        assertEquals(CaptureOutcome.Unrecoverable, PendingCapture(inFlight = "content://b").consume(saved = true))
    }

    @Test
    fun `accepting an import stages the capture and deletes nothing`() {
        val pending = PendingCapture(destination = "content://a")

        val accepted = pending.accept(pending.consume(saved = true))

        assertEquals("content://a", accepted.inFlight)
        assertNull("the destination is spent", accepted.destination)
    }

    @Test
    fun `a capture is deleted only once no import is running`() {
        val pending = PendingCapture(inFlight = "content://a")

        val (running, whileRunning) = pending.afterImport(importing = true)
        assertEquals("content://a", running.inFlight)
        assertNull("deleting mid-read is how a photo becomes unreadable", whileRunning)

        val (done, stale) = running.afterImport(importing = false)
        assertEquals("content://a", stale)
        assertNull(done.inFlight)
    }

    @Test
    fun `a capture left by a dead process is deleted on the first observation`() {
        val (next, stale) = PendingCapture(inFlight = "content://a").afterImport(importing = false)

        assertEquals("content://a", stale)
        assertNull(next.inFlight)
    }

    @Test
    fun `a spent capture cannot import the same photo twice`() {
        val pending = PendingCapture(destination = "content://a")

        assertEquals(CaptureOutcome.Import("content://a"), pending.consume(saved = true))
        assertEquals(CaptureOutcome.Unrecoverable, pending.spent().consume(saved = true))
    }
}
