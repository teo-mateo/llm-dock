package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.prefs.DraftStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json
import java.io.File

/**
 * Where a share lives between the intent and the send (F14). Three records:
 *
 * - **The pending share** — unassigned, staged at intent time and shown on
 *   the target picker. Survives navigation, the Connect round trip, and
 *   process death (F14-R5): the record is a JSON file in [dir] and the
 *   in-memory [pending] is hydrated from it at construction.
 * - **Per-conversation attachments** — written when the user picks a target
 *   ([reassign]), read back by the thread's `load()` so a force-stop between
 *   the pick and the send does not lose the staged image (F14-R5). One file
 *   per attachment, named `0.txt`, `1.txt`…, so removing one renumbers the
 *   rest and the record stays index-aligned with the composer's list.
 * - **The handled token** — the delivery identity of the share this task most
 *   recently claimed, in `handled.json` ([stage] with a token, issue 261).
 *   [clearPending], [reassign] and [clear] deliberately do not clear it: the
 *   claim must outlive the record it refers to, so a redelivery of an already
 *   served intent is refused at intake instead of re-staging a consumed share.
 *
 * [dir] is the app's `cacheDir/shared-drafts` — cache, so the OS may reclaim
 * it, and never backed up. The text half of a share goes through
 * [DraftStore] (existing per-conversation drafts); only attachments live
 * here.
 */
class SharedDraftStore(private val dir: File) {

    private val _pending = MutableStateFlow<StagedShare?>(readPending())
    val pending: StateFlow<StagedShare?> = _pending.asStateFlow()

    private val _handled = MutableStateFlow(readHandledToken())

    /** The last delivery claimed by intake; a redelivery with this token is refused. */
    val handledToken: String? get() = _handled.value

    /**
     * Called at intent time, on the main thread — small files, one-off.
     * [token] records the delivery as handled *before* the pending record is
     * written: the crash window between the two then loses a share (the user
     * re-shares) rather than replaying one, the safe direction for a
     * consume-once flow.
     */
    fun stage(share: StagedShare, token: String? = null) {
        if (token != null) rememberHandled(token)
        writePending(share)
        _pending.value = share
    }

    /** Claims a delivery without staging anything — the [ShareIntake.KeepHydrated] path. */
    fun rememberHandled(token: String) {
        writeHandled(token)
        _handled.value = token
    }

    /** Dismissing the picker, or a share already consumed by a pick. */
    fun clearPending() {
        deletePending()
        _pending.value = null
    }

    /**
     * The picker's "pick a conversation" and the new-chat flow's
     * `onConversationCreated` both land here: the staged text becomes the
     * conversation's draft (the thread's `loadedFrom` already merges it), the
     * attachments move to the per-conversation record, and the pending share
     * is gone.
     */
    fun reassign(conversationId: String, drafts: DraftStore) {
        val share = _pending.value ?: return
        if (share.text.isNotBlank()) drafts.save(conversationId, share.text)
        saveAttachments(conversationId, share.attachments)
        clearPending()
    }

    /**
     * F14-R7 — the summarize claim: one prepared user turn owed to one
     * conversation, written before the thread opens and consumed by its first
     * `load()`. A sibling of [PENDING_FILE] rather than a child of the
     * conversation directory, because [saveAttachments] wipes that directory —
     * a claim filed there would be erased by the attachment write that
     * follows it, cancelling the action the user just took.
     */
    fun stageForAutoSend(conversationId: String, message: String) {
        dir.mkdirs()
        val file = autoSendFile(conversationId)
        val tmp = File(dir, "${file.name}.tmp")
        tmp.writeText(message)
        tmp.renameTo(file)
        clearPending()
    }

    /** Reads the claim and spends it, so no second visit can send it again. */
    suspend fun takeAutoSend(conversationId: String): String? = withContext(Dispatchers.IO) {
        val file = autoSendFile(conversationId)
        if (!file.exists()) return@withContext null
        val message = runCatching { file.readText() }.getOrNull()
        file.delete()
        message?.takeIf { it.isNotBlank() }
    }

    fun saveAttachments(conversationId: String, attachments: List<String>) {
        if (attachments.isEmpty()) return
        val convDir = conversationDir(conversationId).apply { mkdirs() }
        convDir.listFiles().orEmpty().forEach { it.delete() }
        attachments.forEachIndexed { index, dataUrl ->
            File(convDir, "$index.txt").writeText(dataUrl)
        }
    }

    /** Read back the staged attachments for a conversation (F14-R5's force-stop case). */
    suspend fun attachments(conversationId: String): List<String> = withContext(Dispatchers.IO) {
        val files = conversationDir(conversationId).listFiles().orEmpty()
            .sortedBy { it.nameWithoutExtension.toIntOrNull() }
        files.mapNotNull { file -> file.readText().takeIf { it.isNotEmpty() } }
    }

    /**
     * The composer's remove button keeps the record aligned with the on-screen
     * list — the file for that index is deleted and the rest renumbered, so a
     * later re-entry cannot resurrect a removed attachment (F14-R5's "no ghost").
     */
    fun removeAttachment(conversationId: String, index: Int) {
        val convDir = conversationDir(conversationId)
        if (!convDir.exists()) return
        File(convDir, "$index.txt").delete()
        val remaining = convDir.listFiles().orEmpty().sortedBy { it.nameWithoutExtension.toIntOrNull() }
        remaining.forEachIndexed { i, file ->
            if (file.name != "$i.txt") {
                val target = File(convDir, "$i.txt")
                target.delete()
                file.renameTo(target)
            }
        }
    }

    /** Send, or leaving the thread — the staged record is spent. */
    fun clear(conversationId: String) {
        conversationDir(conversationId).deleteRecursively()
        autoSendFile(conversationId).delete()
    }

    private fun autoSendFile(conversationId: String): File = File(dir, "conv_$conversationId.autosend.txt")

    private fun readPending(): StagedShare? {
        val file = File(dir, PENDING_FILE)
        if (!file.exists()) return null
        return runCatching { json.decodeFromString(StagedShare.serializer(), file.readText()) }.getOrNull()
    }

    private fun writePending(share: StagedShare) {
        dir.mkdirs()
        val file = File(dir, PENDING_FILE)
        val tmp = File(dir, "$PENDING_FILE.tmp")
        tmp.writeText(json.encodeToString(StagedShare.serializer(), share))
        tmp.renameTo(file)
    }

    private fun deletePending() {
        File(dir, PENDING_FILE).delete()
        File(dir, "$PENDING_FILE.tmp").delete()
    }

    private fun readHandledToken(): String? {
        val file = File(dir, HANDLED_FILE)
        if (!file.exists()) return null
        return runCatching { json.decodeFromString(String.serializer(), file.readText()) }.getOrNull()
    }

    private fun writeHandled(token: String) {
        dir.mkdirs()
        val file = File(dir, HANDLED_FILE)
        val tmp = File(dir, "$HANDLED_FILE.tmp")
        tmp.writeText(json.encodeToString(String.serializer(), token))
        tmp.renameTo(file)
    }

    private fun conversationDir(conversationId: String): File = File(dir, "conv_$conversationId")

    private companion object {
        const val PENDING_FILE = "pending.json"
        const val HANDLED_FILE = "handled.json"
        val json = Json
    }
}
