package com.hpz.llmdockchat.core.prefs

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.first
import kotlinx.serialization.builtins.MapSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json

/**
 * Unsent composer text, per conversation (F04-R1, F00-R3).
 *
 * Rotation and backgrounding alone would be served by `rememberSaveable`. Disk
 * is what covers the third case: a 401 whose silent re-auth fails routes to
 * Connect with `popUpTo(graph.id)`, which destroys the thread destination and
 * its ViewModel outright — there is no saved instance state left to restore
 * from. F00-R3 requires the draft to still be there afterwards, so it has to
 * outlive the screen.
 */
interface DraftStore {
    suspend fun draft(conversationId: String): String
    fun save(conversationId: String, text: String)
    fun clear(conversationId: String)
}

/**
 * One preferences entry holding a `{conversationId: text}` map, rather than a
 * key per thread: DataStore has no way to enumerate and prune keys by prefix,
 * so per-thread keys would accumulate a row for every conversation ever opened.
 */
class DataStoreDraftStore(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
) : DraftStore {

    private val json = Json
    private val serializer = MapSerializer(String.serializer(), String.serializer())

    private val drafts = ValuePreference(
        dataStore = dataStore,
        name = "composer_drafts",
        scope = scope,
        decode = { raw -> runCatching { json.decodeFromString(serializer, raw) }.getOrNull() },
        encode = { map -> json.encodeToString(serializer, map) },
    )

    override suspend fun draft(conversationId: String): String =
        drafts.flow.first { it !is Stored.Loading }.valueOrNull.orEmpty()[conversationId].orEmpty()

    override fun save(conversationId: String, text: String) {
        if (text.isBlank()) return clear(conversationId)
        val updated = (inMemory() - conversationId) + (conversationId to text)
        // Keeping the newest few is enough for a phone; an unbounded map would
        // grow one entry per thread ever typed in and never shrink.
        drafts.set(updated.entries.toList().takeLast(MAX_DRAFTS).associate { it.toPair() })
    }

    override fun clear(conversationId: String) {
        val existing = inMemory()
        if (conversationId !in existing) return
        drafts.set(existing - conversationId)
    }

    /**
     * The hydrated value without blocking — [ValuePreference.get] would park
     * the caller on a disk read, and these two are called from the main thread
     * on every keystroke. A screen always awaits [draft] before the user can
     * type into it, so hydration has landed by the time either runs.
     */
    private fun inMemory(): Map<String, String> = drafts.flow.value.valueOrNull.orEmpty()

    private companion object {
        const val MAX_DRAFTS = 20
    }
}
