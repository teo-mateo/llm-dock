package com.hpz.llmdockchat.core.prefs

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.first

/**
 * What the new-chat sheet remembers across app restarts (F03-R1's fourth
 * criterion, F03-R3's second). Unlike [com.hpz.llmdockchat.core.net.ServerUrlStore]
 * or [com.hpz.llmdockchat.core.auth.TokenStore], nothing here is read from an
 * OkHttp callback thread — every caller is already inside a ViewModel
 * coroutine — so the interface is plain `suspend`, not the blocking
 * `get()`/`StateFlow` shape those two need.
 */
interface NewChatPreferences {
    /** The raw `main_service` wire value used last time, or null if there was no prior chat. */
    suspend fun lastModel(): String?
    fun rememberModel(mainService: String)

    /** MCP server ids enabled on the last thread created here. */
    suspend fun lastMcpServerIds(): List<String>
    fun rememberMcpServerIds(ids: List<String>)
}

class DataStoreNewChatPreferences(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
) : NewChatPreferences {

    private val modelPref = ValuePreference(
        dataStore = dataStore,
        name = "new_chat_last_model",
        scope = scope,
        decode = { it.takeIf(String::isNotBlank) },
        encode = { it },
    )

    // MCP server ids are dashboard-defined slugs (`sympy-math`, `websearch`,
    // …) — never containing a comma — so a plain join/split is enough and
    // avoids pulling a JSON codec into a preferences file.
    private val mcpServersPref = ValuePreference(
        dataStore = dataStore,
        name = "new_chat_last_mcp_servers",
        scope = scope,
        decode = { raw -> raw.split(",").filter(String::isNotBlank) },
        encode = { ids -> ids.joinToString(",") },
    )

    override suspend fun lastModel(): String? =
        modelPref.flow.first { it !is Stored.Loading }.valueOrNull

    override fun rememberModel(mainService: String) = modelPref.set(mainService)

    override suspend fun lastMcpServerIds(): List<String> =
        mcpServersPref.flow.first { it !is Stored.Loading }.valueOrNull.orEmpty()

    override fun rememberMcpServerIds(ids: List<String>) = mcpServersPref.set(ids)
}
