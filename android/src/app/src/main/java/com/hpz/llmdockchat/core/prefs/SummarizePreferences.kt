package com.hpz.llmdockchat.core.prefs

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.first

/**
 * The two values behind F16's summarize row, and the only place either is
 * stated. The prompt is an app constant because the issue asks for instructions
 * in the *first user message*, not a system prompt — the managed prompts at
 * `GET /api/chat/prompts` are system prompts and are not this. The tool ids are
 * machine-local on the server (`mcp_servers.json`), so they are configured here
 * rather than hardcoded into the request path.
 */
object SummarizeDefaults {
    const val PROMPT =
        "Read the page at the link below and give me a summary, then explain what it's " +
            "actually about and why it might matter. Use your fetch tool to read it; search " +
            "if the page references something you need context on. If the page can't be read, " +
            "say so plainly instead of guessing at its contents."

    /** First-read preselection, kept in this order. Only ids the registry reports survive. */
    val TOOL_IDS = listOf("webfetch", "websearch")

    /**
     * The tools a summarize turn will actually get: the stored selection, or the
     * preselection when nothing has ever been stored, narrowed to ids the
     * registry reports right now. Empty means the summarize row must stay
     * hidden — a summarize turn with no fetch tool is a model inventing the
     * contents of a URL it never read.
     */
    fun effectiveTools(stored: List<String>?, available: List<String>): List<String> {
        val present = available.toSet()
        return (stored ?: TOOL_IDS).filter { it in present }
    }
}

interface SummarizePreferences {
    /** Null until the user edits the prompt — null means [SummarizeDefaults.PROMPT]. */
    suspend fun promptOverride(): String?

    /** A blank [text] clears the override rather than storing an empty prompt. */
    fun setPromptOverride(text: String)

    /** Null means "never chosen", which is what makes the first-read preselection possible. */
    suspend fun toolIds(): List<String>?
    fun setToolIds(ids: List<String>)
}

class DataStoreSummarizePreferences(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
) : SummarizePreferences {

    private val promptPref = ValuePreference(
        dataStore = dataStore,
        name = "summarize_prompt",
        scope = scope,
        decode = { it.takeIf(String::isNotBlank) },
        encode = { it },
    )

    // MCP server ids are dashboard-defined slugs that never contain a comma, so
    // a join/split avoids a JSON codec in a preferences file — same trade as
    // NewChatPreferences' tool list.
    private val toolsPref = ValuePreference(
        dataStore = dataStore,
        name = "summarize_tools",
        scope = scope,
        decode = { raw -> raw.split(",").filter(String::isNotBlank) },
        encode = { ids -> ids.joinToString(",") },
    )

    override suspend fun promptOverride(): String? =
        promptPref.flow.first { it !is Stored.Loading }.valueOrNull

    override fun setPromptOverride(text: String) {
        if (text.isBlank()) promptPref.clear() else promptPref.set(text)
    }

    override suspend fun toolIds(): List<String>? =
        toolsPref.flow.first { it !is Stored.Loading }.valueOrNull

    override fun setToolIds(ids: List<String>) = toolsPref.set(ids)
}

/** For previews and tests — holds the values, persists nothing. */
class InMemorySummarizePreferences(
    private var prompt: String? = null,
    private var tools: List<String>? = null,
) : SummarizePreferences {
    override suspend fun promptOverride(): String? = prompt
    override fun setPromptOverride(text: String) {
        prompt = text.takeIf(String::isNotBlank)
    }

    override suspend fun toolIds(): List<String>? = tools
    override fun setToolIds(ids: List<String>) {
        tools = ids
    }
}
