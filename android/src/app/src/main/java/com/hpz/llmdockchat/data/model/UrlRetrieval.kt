package com.hpz.llmdockchat.data.model

/** A server whose tools can read a given URL (issue 255 / F14-R7). */
data class UrlFetchServer(val id: String, val name: String, val tools: List<String>)

/** A probe candidate the dashboard could not reach — configured, but not answering. */
data class UrlFetchFailure(val id: String, val error: String)

/**
 * What the dashboard says about page retrieval. [supported] is false when the
 * server returned no `url_fetch` block at all — an older dashboard, which must
 * read as "this phone can't know", never as "no tools are configured", because
 * the two need different things from the user.
 */
data class UrlRetrieval(
    val supported: Boolean,
    val servers: List<UrlFetchServer>,
    val failures: List<UrlFetchFailure>,
) {
    val isAvailable: Boolean get() = servers.isNotEmpty()

    val serverIds: List<String> get() = servers.map { it.id }

    companion object {
        val UNSUPPORTED = UrlRetrieval(supported = false, servers = emptyList(), failures = emptyList())
    }
}
