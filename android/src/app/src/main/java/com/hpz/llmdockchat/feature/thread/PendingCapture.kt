package com.hpz.llmdockchat.feature.thread

import androidx.compose.runtime.saveable.Saver
import androidx.compose.runtime.saveable.listSaver

/**
 * The camera capture in flight: the destination handed to the camera app, and
 * the capture whose import has not finished.
 *
 * Saved state rather than `remember`: the camera app is foreground while this
 * activity is stopped, which is exactly where the process gets reclaimed, and
 * the activity-result registry still delivers the result on return. Without the
 * destination the photo is dropped with no way to tell it apart from a cancel.
 */
data class PendingCapture(
    val destination: String? = null,
    val inFlight: String? = null,
) {

    /** What the camera's result means, before anything is done about it. */
    fun consume(saved: Boolean): CaptureOutcome = when {
        destination == null -> CaptureOutcome.Unrecoverable
        !saved -> CaptureOutcome.Discard(destination)
        else -> CaptureOutcome.Import(destination)
    }

    /** The state after a result has been handled: the destination is spent. */
    fun spent(): PendingCapture = copy(destination = null)

    companion object {
        val Saver: Saver<PendingCapture, Any> = listSaver(
            save = { listOf(it.destination.orEmpty(), it.inFlight.orEmpty()) },
            restore = {
                PendingCapture(
                    destination = it[0].ifEmpty { null },
                    inFlight = it[1].ifEmpty { null },
                )
            },
        )
    }
}

sealed interface CaptureOutcome {
    /** The camera wrote a capture that should be imported. */
    data class Import(val uri: String) : CaptureOutcome

    /** The user backed out: the capture is ours to delete. */
    data class Discard(val uri: String) : CaptureOutcome

    /** A result arrived with no destination to read — the photo is gone. */
    data object Unrecoverable : CaptureOutcome
}
