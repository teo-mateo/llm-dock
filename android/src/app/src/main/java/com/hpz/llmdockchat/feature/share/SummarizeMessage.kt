package com.hpz.llmdockchat.feature.share

/**
 * The user turn a summarize tap sends (F14-R7).
 *
 * The grounding contract travels in the user message rather than the system
 * prompt: it stays visible in the transcript, and `main_system_prompt` would
 * overwrite the operator's own configured default. No server or tool id is
 * named here — the backend injects each enabled server's own hint, and a hard
 * tool name here would break on any install that names its fetcher otherwise.
 */
object SummarizeMessage {
    fun build(url: String): String = """
        |Summarise this page.
        |
        |$url
        |
        |Use the available URL-fetching tool to read the page first, then summarise what the fetched content actually says.
        |If the fetch fails, is blocked, or returns nothing useful, say exactly which of those happened and stop.
        |Do not summarise from the URL, the site name, or prior knowledge.
    """.trimMargin()

    /** The host, for the action's label — a bare `https://…` is too long to read. */
    fun domain(url: String): String {
        val afterScheme = url.substringAfter("://", "")
        if (afterScheme.isEmpty()) return "this page"
        val host = afterScheme.takeWhile { it != '/' && it != '?' && it != '#' }
        val withoutAuth = host.substringAfterLast('@')
        return withoutAuth.substringBefore(':').ifBlank { "this page" }
    }
}
