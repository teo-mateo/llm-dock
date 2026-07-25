package com.hpz.llmdockchat.core.prefs

/**
 * A stored value that may not have been read off disk yet.
 *
 * The distinction matters: "not read yet" and "not set" are the same `null`,
 * and a screen that conflates them shows "not configured" for a frame before
 * flipping to the real value.
 */
sealed interface Stored<out T> {
    data object Loading : Stored<Nothing>
    data class Ready<out T>(val value: T?) : Stored<T>
}

val <T> Stored<T>.valueOrNull: T?
    get() = (this as? Stored.Ready)?.value
