package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.data.model.UrlRetrieval

/**
 * What the picker offers for the staged share.
 *
 * [Blocked] is deliberate: a share of a page with no way to read that page
 * gets a reason and a next step, never a summarize turn. Sending one anyway
 * would hand the model a URL and no way to open it, which is how a shared
 * link ends up answered from prior knowledge while looking like a summary.
 */
sealed interface SummarizeOption {
    /** Not a text share with a link — an image, a text file, or prose about something else. */
    data object NotShared : SummarizeOption

    /** The probe is still in flight. */
    data object Checking : SummarizeOption

    data class Ready(val url: String, val serverIds: List<String>) : SummarizeOption

    data class Blocked(val reason: String) : SummarizeOption

    companion object {
        /** The probe itself didn't answer — a different fix than having no tool. */
        val UNREACHABLE = Blocked(
            "Couldn't reach the dashboard to check for a page-fetch tool. Retry, or send the link yourself.",
        )

        fun of(share: StagedShare, retrieval: UrlRetrieval?): SummarizeOption {
            val url = share.url ?: return NotShared
            if (share.error != null || share.attachments.isNotEmpty()) return NotShared
            if (retrieval == null) return Checking
            if (!retrieval.supported) {
                return Blocked(
                    "This dashboard can't report which tools fetch a page, so there's nothing to summarise with. " +
                        "Update llm-dock, or send the link yourself.",
                )
            }
            if (retrieval.isAvailable) return Ready(url, retrieval.serverIds)
            val names = retrieval.failures.joinToString(", ") { it.id }
            return Blocked(
                if (retrieval.failures.isEmpty()) {
                    "No tool on this dashboard can fetch a web page. Enable one under Tools, or send the link yourself."
                } else {
                    "The page-fetch tool didn't answer ($names). Check it under Tools, then retry."
                },
            )
        }
    }
}
