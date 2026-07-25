package com.hpz.llmdockchat.feature.models

import com.hpz.llmdockchat.core.time.Timestamps
import com.hpz.llmdockchat.data.model.ServiceSummary
import java.time.Instant
import java.time.ZoneId
import kotlin.math.roundToInt

/**
 * Pure formatting, split out of the Compose layer so it can be unit tested
 * without Robolectric (Architecture Part IV — logic criteria need only a JVM
 * test).
 */

/** F10-R1: "not-created" distinguishable from "exited", which carries its exit code. */
fun ServiceSummary.statusLabel(): String = when {
    isRunning -> "Running"
    isExited -> exitCode?.let { "Exited (code $it)" } ?: "Exited"
    isNotCreated -> "Not created"
    else -> status.ifBlank { "Unknown" }
}

/**
 * The row's second line. Deliberately never says "uptime" — the payload only
 * carries the container's creation time, not its last start, so a restarted
 * container would show a wrong number under that name (F10's Deviations).
 * "created … ago" is honest about what the timestamp actually is.
 */
fun ServiceSummary.subtitle(now: Instant, zone: ZoneId): String = buildList {
    if (port > 0) add(":$port")
    when {
        isRunning -> {
            modelSizeStr?.let(::add)
            createdAt?.let { add("created ${Timestamps.relative(it, now, zone)}") }
        }
        isExited -> {
            modelSizeStr?.let(::add)
            add(exitCode?.let { "exited (code $it)" } ?: "exited")
        }
        isNotCreated -> {
            if (modelSizeStr != null) add("needs ~$modelSizeStr") else add("not created")
        }
        else -> {
            modelSizeStr?.let(::add)
            add(status.ifBlank { "unknown" })
        }
    }
}.joinToString(" · ")

/** MiB -> GiB, one decimal — the same unit `nvidia-smi` reports, just relabelled GB for the header. */
fun mibToGb(mib: Int): String {
    val gb = mib / 1024.0
    val rounded = (gb * 10).roundToInt() / 10.0
    return if (rounded == rounded.toLong().toDouble()) "${rounded.toLong()}" else rounded.toString()
}
