package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.data.model.PiSession

fun formatAgo(nowMs: Long, thenMs: Long): String {
    val elapsed = nowMs - thenMs
    return when {
        elapsed < 60_000L -> "now"
        elapsed < 3_600_000L -> "${elapsed / 60_000L} min ago"
        elapsed < 86_400_000L -> "${elapsed / 3_600_000L} h ago"
        else -> "${elapsed / 86_400_000L} d ago"
    }
}

fun formatCacheBytes(bytes: Long): String {
    val kib = 1024.0
    val mib = kib * 1024
    return if (bytes < mib) "${Math.ceil(bytes / kib).toLong()} KB" else "%.1f MB".format(bytes / mib)
}

fun piSessionTitle(session: PiSession): String =
    session.name?.takeIf { it.isNotBlank() }
        ?: session.cwd.trimEnd('/').split('/').lastOrNull()?.takeIf { it.isNotBlank() }
        ?: session.cwd

fun piSessionMetaHead(cwd: String, model: String?): String =
    listOfNotNull(model?.takeIf { it.isNotBlank() }, shortCwd(cwd)).joinToString(" · ")

private fun shortCwd(cwd: String): String? {
    val segments = cwd.trimEnd('/').split('/').filter { it.isNotBlank() }
    return segments.takeLast(2).joinToString("/").takeIf { it.isNotBlank() }
}

fun piContextLabel(contextPercent: Double?): String? = contextPercent?.let { "ctx ${Math.round(it)}%" }

data class FollowState(val following: Boolean, val seen: Any?) {
    fun hasUnseen(current: Any?): Boolean = !following && current !== seen
    fun pause(current: Any?): FollowState = FollowState(following = false, seen = current)
    fun settle(atBottom: Boolean, current: Any?): FollowState = FollowState(following = atBottom, seen = current)
    fun jump(current: Any?): FollowState = FollowState(following = true, seen = current)
}
