package com.hpz.llmdockchat.feature.pi

fun formatAgo(nowMs: Long, thenMs: Long): String {
    val elapsed = nowMs - thenMs
    return when {
        elapsed < 60_000L -> "now"
        elapsed < 3_600_000L -> "${elapsed / 60_000L} min ago"
        elapsed < 86_400_000L -> "${elapsed / 3_600_000L} h ago"
        else -> "${elapsed / 86_400_000L} d ago"
    }
}
