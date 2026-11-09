package com.hpz.llmdockchat.feature.pi.transcript.tools

import com.hpz.llmdockchat.feature.pi.transcript.PiItem
import com.hpz.llmdockchat.feature.pi.transcript.ToolStatus
import java.util.Locale

fun toolStatusText(item: PiItem.Tool): String = when (item.status) {
    ToolStatus.RUNNING -> "running…"
    ToolStatus.DONE -> item.durationMs?.takeIf { it != 0L }?.let { durationText(it) } ?: ""
    ToolStatus.ERROR -> "error"
}

fun toolStatusDescription(item: PiItem.Tool): String = when (item.status) {
    ToolStatus.DONE -> item.durationMs?.let { "done · ${durationText(it)}" } ?: "done"
    else -> toolStatusText(item)
}

private fun durationText(ms: Long): String =
    if (ms < 1000) "$ms ms" else String.format(Locale.ROOT, "%.1f s", ms / 1000.0)
