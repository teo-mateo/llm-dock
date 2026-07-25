package com.hpz.llmdockchat.core.net

/**
 * Server-Sent Events framing, and nothing else.
 *
 * Feed it one line at a time; it returns a payload when a blank line closes an
 * event. It does **not** look inside a payload — `[DONE]`, a heartbeat and a
 * typed frame are all just strings here, and the consumer decides what they
 * mean (Architecture D2).
 */
class SseFrameParser {

    private val data = StringBuilder()
    private var open = false

    /** @return the completed payload, or null if the event is still open. */
    fun onLine(rawLine: String): String? {
        val line = rawLine.removeSuffix("\r")

        if (line.isEmpty()) return dispatch()
        if (line.startsWith(":")) return null

        val separator = line.indexOf(':')
        val field = if (separator < 0) line else line.substring(0, separator)
        if (field != "data") return null

        var value = if (separator < 0) "" else line.substring(separator + 1)
        if (value.startsWith(" ")) value = value.substring(1)

        if (open) data.append('\n')
        data.append(value)
        open = true
        return null
    }

    private fun dispatch(): String? {
        if (!open) return null
        val payload = data.toString()
        data.setLength(0)
        open = false
        return payload
    }
}
