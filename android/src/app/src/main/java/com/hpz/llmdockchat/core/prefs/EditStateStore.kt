package com.hpz.llmdockchat.core.prefs

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.MapSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json

/**
 * The half of an open edit that cannot be re-derived from the server: which
 * message is being edited, and the draft the edit clobbered (the Cancel
 * target). The edit text itself is not stored — while an edit is open,
 * `DraftStore` mirrors the live composer, so the text rides the draft path.
 *
 * Attachments are deliberately excluded: picked draft attachments do not
 * survive process death anywhere in this app, and image data URLs are
 * multi-megabyte values with no home in preferences. A restored edit takes
 * its attachments from the fresh message row, like `beginEdit` does.
 */
@Serializable
data class EditSession(val messageId: String, val composerBeforeEdit: String)

/**
 * Edit mode across process death. Rotation and backgrounding are
 * served by the surviving ViewModel; disk is for the case that destroys it —
 * the failed-reauth Connect round trip and force-stop, both of which land on
 * a cold `load()` with no edit state in memory.
 */
interface EditStateStore {
    suspend fun record(conversationId: String): EditSession?
    fun save(conversationId: String, session: EditSession)
    fun clear(conversationId: String)
}

/**
 * One preferences entry holding a `{conversationId: EditSession}` map, same
 * shape and same reasoning as [DataStoreDraftStore]: per-thread keys cannot be
 * enumerated and pruned, so they would accumulate one row per conversation.
 */
class DataStoreEditStateStore(
    dataStore: DataStore<Preferences>,
    scope: CoroutineScope,
) : EditStateStore {

    private val json = Json
    private val serializer = MapSerializer(String.serializer(), EditSession.serializer())

    private val editDrafts = ValuePreference(
        dataStore = dataStore,
        name = "edit_drafts",
        scope = scope,
        decode = { raw -> runCatching { json.decodeFromString(serializer, raw) }.getOrNull() },
        encode = { map -> json.encodeToString(serializer, map) },
    )

    override suspend fun record(conversationId: String): EditSession? =
        editDrafts.flow.first { it !is Stored.Loading }.valueOrNull.orEmpty()[conversationId]

    override fun save(conversationId: String, session: EditSession) {
        val updated = (inMemory() - conversationId) + (conversationId to session)
        editDrafts.set(updated.entries.toList().takeLast(MAX_EDIT_SESSIONS).associate { it.toPair() })
    }

    override fun clear(conversationId: String) {
        val existing = inMemory()
        if (conversationId !in existing) return
        editDrafts.set(existing - conversationId)
    }

    /** The hydrated value without blocking — same contract as [DataStoreDraftStore.inMemory]. */
    private fun inMemory(): Map<String, EditSession> = editDrafts.flow.value.valueOrNull.orEmpty()

    private companion object {
        const val MAX_EDIT_SESSIONS = 20
    }
}
