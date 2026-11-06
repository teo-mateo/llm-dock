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

fun piSessionMetaHead(cwd: String, model: String?): String =
    listOfNotNull(cwd.takeIf { it.isNotBlank() }, model?.takeIf { it.isNotBlank() }).joinToString(" · ")

fun piContextLabel(contextPercent: Double?): String? = contextPercent?.let { "ctx ${Math.round(it)}%" }

data class FollowState(val following: Boolean, val seen: Any?) {
    fun hasUnseen(current: Any?): Boolean = !following && current !== seen
    fun pause(current: Any?): FollowState = FollowState(following = false, seen = current)
    fun settle(atBottom: Boolean, current: Any?): FollowState = FollowState(following = atBottom, seen = current)
    fun jump(current: Any?): FollowState = FollowState(following = true, seen = current)
}
