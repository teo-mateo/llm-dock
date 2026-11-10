package com.hpz.llmdockchat.feature.thread

/**
 * Whether a send may start. One source for the question: the composer's Send and
 * the edit confirmation both ask it, so a screen that blocks on outstanding
 * settings writes cannot be bypassed through the other path.
 */
fun interface SendGate {
    fun blocked(): Boolean
}
