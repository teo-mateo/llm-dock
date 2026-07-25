package com.hpz.llmdockchat.core.net

/**
 * How long to wait before the next reconnect attempt (F09-R4).
 *
 * Two things have to be true at once, and they pull in opposite directions: the
 * app must not hammer a server that is not there, and it must not give up
 * permanently either — a phone comes out of a tunnel ten minutes later and the
 * run it left behind is still on the dashboard. So the delay grows, and then
 * stops growing. There is no attempt limit and no sentinel meaning "stop": the
 * only thing that ends the loop is the collector going away.
 *
 * Pure and separately tested ([com.hpz.llmdockchat.core.net.ReconnectBackoff]
 * holds only an attempt counter), so the schedule can be asserted without
 * waiting for any of it.
 */
fun reconnectDelayMs(attempt: Int, initialMs: Long, maxMs: Long): Long {
    require(initialMs > 0) { "initialMs must be positive" }
    val ceiling = maxOf(initialMs, maxMs)
    if (attempt <= 0) return initialMs
    // Doubling in the exponent rather than in a loop keeps a long offline spell
    // from overflowing on the way to a value that is capped anyway.
    val shift = attempt.coerceAtMost(Long.SIZE_BITS - 2)
    val grown = initialMs shl shift
    return if (grown <= 0L) ceiling else minOf(grown, ceiling)
}

/**
 * The stateful half: one instance per run being collected.
 *
 * [reset] is called after an attempt that actually delivered frames, so a
 * connection that keeps dropping *after* connecting starts over at the short
 * delay instead of inheriting the long one a previous outage earned.
 */
class ReconnectBackoff(
    private val initialMs: Long = DEFAULT_INITIAL_MS,
    private val maxMs: Long = DEFAULT_MAX_MS,
) {
    private var attempt = 0

    fun next(): Long = reconnectDelayMs(attempt++, initialMs, maxMs)

    fun reset() {
        attempt = 0
    }

    companion object {
        /**
         * A LAN blip is over in well under a second, so the first retry is
         * quick; airplane mode is not, so it backs off to eight seconds — long
         * enough not to be hammering, short enough that coming back on wifi
         * catches up while the phone is still in your hand.
         *
         * Deliberately not [com.hpz.llmdockchat.data.ServicesStreamRepository]'s
         * flat 2 s. That stream is scoped to a sheet that is visible for
         * seconds; a thread can sit reconnecting for as long as the screen is
         * open, which is exactly the case a flat delay handles badly.
         */
        const val DEFAULT_INITIAL_MS = 1_000L
        const val DEFAULT_MAX_MS = 8_000L
    }
}
