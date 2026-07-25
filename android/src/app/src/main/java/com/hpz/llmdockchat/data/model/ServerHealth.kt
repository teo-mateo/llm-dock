package com.hpz.llmdockchat.data.model

/**
 * A domain type, not the wire shape: features never see a DTO (Architecture D6).
 * `status == "healthy"` is decided once, here, rather than string-compared at
 * every call site.
 */
data class ServerHealth(
    val healthy: Boolean,
    val status: String,
    val version: String?,
    val dockerAvailable: Boolean,
    val nvidiaAvailable: Boolean,
)
