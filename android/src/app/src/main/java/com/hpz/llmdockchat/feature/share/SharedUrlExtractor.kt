package com.hpz.llmdockchat.feature.share

/**
 * The URL a share is actually about. Only a `text/plain` share is
 * ever scanned — a text file inlined as a fenced block routinely contains
 * links and is not a shared page — and the first match wins, because a share
 * of the form `title url` or `url (via …)` names one page.
 */
object SharedUrlExtractor {
    private val URL = Regex("""https?://\S+""", RegexOption.IGNORE_CASE)

    /** Punctuation a sharer appends after the link, never part of it. */
    private const val TRAILING = ".,;:!?)]}>\"'”’»"

    fun firstUrl(text: String): String? {
        for (match in URL.findAll(text)) {
            val candidate = match.value.trimEnd { it in TRAILING }
            if (candidate.hasHost()) return candidate
        }
        return null
    }

    private fun String.hasHost(): Boolean {
        val separator = indexOf("://")
        if (separator < 0) return false
        val host = substring(separator + 3).takeWhile { it != '/' && it != '?' && it != '#' }
        return host.isNotEmpty()
    }
}
