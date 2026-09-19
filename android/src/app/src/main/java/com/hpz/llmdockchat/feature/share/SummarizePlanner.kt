package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.prefs.SummarizeDefaults
import com.hpz.llmdockchat.data.model.ModelRef
import com.hpz.llmdockchat.data.model.ServiceSummary
import com.hpz.llmdockchat.data.model.parseModelRef

/**
 * What the F16 summarize row does when tapped. [Hidden] covers every reason the
 * row is absent — the row and the action share one decision so the two cannot
 * disagree about when the path is offered at all.
 */
sealed interface SummarizePlan {
    data object Hidden : SummarizePlan

    /** The remembered model is usable: create on it, put the tools on, send. */
    data class CreateOn(val modelService: String, val message: String, val toolIds: List<String>) : SummarizePlan

    /** No usable remembered model — F03-R1 refuses a thread on a dead model, so the sheet asks. */
    data class PickModelFirst(val message: String, val toolIds: List<String>) : SummarizePlan
}

/**
 * The whole F16 decision in one pure function: eligibility is a property of the
 * staged share plus the configured tools, and the routing is a property of the
 * remembered model, so a tap on the row can be tested without a server.
 */
object SummarizePlanner {

    /**
     * The URL to summarize, or null when the row must stay hidden: only a
     * text-classified share counts, so an inlined text file that happens to
     * quote a URL — or an image share, or a rejected one — never offers the row.
     */
    fun urlIn(share: StagedShare?): String? {
        if (share == null || share.error != null || share.attachments.isNotEmpty()) return null
        if (share.origin != StagedOrigin.TEXT) return null
        return URL_IN_TEXT.find(share.text)?.value?.trimEnd { it in TRAILING_PUNCTUATION }
    }

    fun message(prompt: String, url: String): String = "$prompt\n\n$url"

    fun plan(
        share: StagedShare?,
        prompt: String,
        storedToolIds: List<String>?,
        registry: List<String>,
        rememberedModel: String?,
        services: List<ServiceSummary>,
    ): SummarizePlan {
        val tools = SummarizeDefaults.effectiveTools(storedToolIds, registry)
        if (tools.isEmpty()) return SummarizePlan.Hidden
        val url = urlIn(share) ?: return SummarizePlan.Hidden
        val message = message(prompt, url)
        val model = rememberedModel?.takeIf { usable(it, services) }
            ?: return SummarizePlan.PickModelFirst(message, tools)
        return SummarizePlan.CreateOn(model, message, tools)
    }

    /**
     * Same bar the new-chat sheet holds itself to (F03-R1's fourth criterion):
     * a local model must be present, chat-capable and running. A remote model
     * is never gated on state the phone cannot see, and the sheet accepts a
     * remote id that left the curated list, so both are usable here.
     */
    private fun usable(wireValue: String, services: List<ServiceSummary>): Boolean =
        when (val ref = parseModelRef(wireValue)) {
            is ModelRef.Local -> services.find { it.name == ref.serviceName }
                ?.let { it.isChatCapable && it.isRunning } == true
            is ModelRef.OpenRouter -> true
        }

    private val URL_IN_TEXT = Regex("https?://\\S+")

    /** Trailing punctuation a sharing app glued to the link — `)` and `.` are not part of a URL. */
    private val TRAILING_PUNCTUATION = charArrayOf('.', ',', ';', ':', '!', '?', ')', ']', '>', '\u201d', '\u2019')
}
