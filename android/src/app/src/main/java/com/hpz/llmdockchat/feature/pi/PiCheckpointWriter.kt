package com.hpz.llmdockchat.feature.pi

import com.hpz.llmdockchat.feature.pi.transcript.PiSessionSnapshot
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

internal class PiCheckpointWriter(
    private val scope: CoroutineScope,
    private val elapsedMillis: () -> Long = { System.nanoTime() / 1_000_000 },
    private val save: (PiSessionSnapshot) -> Unit,
) {
    private val lock = Any()
    private var latest: PiSessionSnapshot? = null
    private var lastSave: Long? = null
    private var timer: Job? = null
    private var closed = false

    fun changed(snapshot: PiSessionSnapshot) = synchronized(lock) {
        if (closed) return@synchronized
        latest = snapshot
        val remaining = lastSave?.let { INTERVAL_MS - (elapsedMillis() - it) } ?: 0
        if (remaining <= 0) {
            flushLocked()
        } else if (timer == null) {
            timer = scope.launch {
                delay(remaining)
                synchronized(lock) {
                    timer = null
                    if (!closed) flushLocked()
                }
            }
        }
    }

    fun flush() = synchronized(lock) { if (!closed) flushLocked() }

    fun close(flush: Boolean = true) = synchronized(lock) {
        if (flush && !closed) flushLocked()
        closed = true
        latest = null
        timer?.cancel()
        timer = null
    }

    private fun flushLocked() {
        timer?.cancel()
        timer = null
        val snapshot = latest ?: return
        latest = null
        lastSave = elapsedMillis()
        save(snapshot)
    }

    companion object {
        const val INTERVAL_MS = 5_000L
    }
}
