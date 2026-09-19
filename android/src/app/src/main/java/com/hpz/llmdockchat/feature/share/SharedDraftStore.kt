package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.prefs.DraftStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json
import java.io.File

/**
 * Where a share lives between the intent and the send (F14). Two shapes:
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
 *
 * [dir] is the app's `cacheDir/shared-drafts` — cache, so the OS may reclaim
 * it, and never backed up. The text half of a share goes through
 * [DraftStore] (existing per-conversation drafts); only attachments live
 * here.
 *
 * The same per-conversation directory also carries F16's two summarize records
 * (`autosend`, `notice.txt`), because they share F14's lifetime exactly: armed
 * before navigation, spent on send, gone on leave. They are not attachment
 * files and [attachmentFiles] keeps them out of that list.
 */
class SharedDraftStore(private val dir: File) {

    private val _pending = MutableStateFlow<StagedShare?>(readPending())
    val pending: StateFlow<StagedShare?> = _pending.asStateFlow()

    private var armedSummarize: SummarizeIntent? = readSummarize()

    /** Called at intent time, on the main thread — small files, one-off. */
    fun stage(share: StagedShare) {
        writeRecord(PENDING_FILE, StagedShare.serializer(), share)
        _pending.value = share
    }

    /** Dismissing the picker, or a share already consumed by a pick. */
    fun clearPending() {
        dropPending()
        clearSummarize()
    }

    // -- F16 summarize ------------------------------------------------------

    /**
     * Armed by the picker row when the remembered model is not usable, so the
     * new-chat sheet can preselect the tools and the message survives being
     * picked. Cleared with the share it came from ([clearPending]) or once a
     * created conversation has taken it ([consumeSummarize]).
     */
    fun armSummarize(intent: SummarizeIntent) {
        writeRecord(SUMMARIZE_FILE, SummarizeIntent.serializer(), intent)
        armedSummarize = intent
    }

    fun peekSummarize(): SummarizeIntent? = armedSummarize

    /** Delete the armed intent without staging it anywhere. */
    fun clearSummarize() {
        deleteRecord(SUMMARIZE_FILE)
        armedSummarize = null
    }

    /**
     * Written before navigating to a thread whose first turn must send itself.
     * On disk *before* the navigation because process death between the two is
     * the window this feature lives in; consumed by [takeAutoSend].
     */
    fun armAutoSend(conversationId: String) {
        conversationDir(conversationId).mkdirs()
        File(conversationDir(conversationId), AUTOSEND_FILE).writeText("1")
    }

    /**
     * Consume-once: the marker is gone before the caller sends, so a thread
     * visited twice produces one turn and not two. The server's one-active-run
     * 409 is a backstop, not the design.
     */
    suspend fun takeAutoSend(conversationId: String): Boolean = withContext(Dispatchers.IO) {
        val marker = File(conversationDir(conversationId), AUTOSEND_FILE)
        val armed = marker.exists()
        marker.delete()
        armed
    }

    /** Why a staged summarize message was left unsent, read back by the thread's `load()`. */
    fun saveNotice(conversationId: String, notice: String) {
        conversationDir(conversationId).mkdirs()
        File(conversationDir(conversationId), NOTICE_FILE).writeText(notice)
    }

    suspend fun notice(conversationId: String): String? = withContext(Dispatchers.IO) {
        val file = File(conversationDir(conversationId), NOTICE_FILE)
        if (!file.exists()) null else file.readText().takeIf(String::isNotBlank)
    }

    /**
     * Stage [SummarizeIntent.message] for a freshly created conversation and arm
     * the auto-send — or withhold it. A summarize turn whose tools could not be
     * enabled is a model inventing the contents of a URL it cannot read, so on
     * that path the auto-send deviation is withdrawn and the reason is staged
     * with the message.
     */
    fun consumeSummarize(conversationId: String, drafts: DraftStore, toolsApplied: Boolean) {
        val intent = armedSummarize ?: return
        stageForConversation(conversationId, drafts, intent.message)
        if (toolsApplied) {
            armAutoSend(conversationId)
        } else {
            saveNotice(conversationId, TOOLS_NOT_ENABLED_NOTICE)
        }
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
        stageForConversation(conversationId, drafts, share.text)
    }

    /**
     * F16's handoff: the same move as [reassign] but with a composed message
     * instead of the raw shared text — the summarize prompt plus the link, not
     * the title-and-link a share carries. Clears the whole share lifecycle, the
     * armed summarize intent included.
     */
    fun stageForConversation(conversationId: String, drafts: DraftStore, message: String) {
        if (message.isNotBlank()) drafts.save(conversationId, message)
        _pending.value?.attachments?.let { saveAttachments(conversationId, it) }
        dropPending()
        clearSummarize()
    }

    fun saveAttachments(conversationId: String, attachments: List<String>) {
        if (attachments.isEmpty()) return
        val convDir = conversationDir(conversationId).apply { mkdirs() }
        attachmentFiles(convDir).forEach { it.delete() }
        attachments.forEachIndexed { index, dataUrl ->
            File(convDir, "$index.txt").writeText(dataUrl)
        }
    }

    /** Read back the staged attachments for a conversation (F14-R5's force-stop case). */
    suspend fun attachments(conversationId: String): List<String> = withContext(Dispatchers.IO) {
        attachmentFiles(conversationDir(conversationId)).mapNotNull { file ->
            file.readText().takeIf { it.isNotEmpty() }
        }
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
        attachmentFiles(convDir).forEachIndexed { i, file ->
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
    }

    private fun readPending(): StagedShare? = readRecord(PENDING_FILE, StagedShare.serializer())

    private fun readSummarize(): SummarizeIntent? =
        readRecord(SUMMARIZE_FILE, SummarizeIntent.serializer())

    /** A record that will not decode is treated as absent, never as a crash. */
    private fun <T> readRecord(name: String, serializer: KSerializer<T>): T? {
        val file = File(dir, name)
        if (!file.exists()) return null
        return runCatching { json.decodeFromString(serializer, file.readText()) }.getOrNull()
    }

    private fun <T> writeRecord(name: String, serializer: KSerializer<T>, value: T) {
        dir.mkdirs()
        val file = File(dir, name)
        val tmp = File(dir, "$name.tmp")
        tmp.writeText(json.encodeToString(serializer, value))
        tmp.renameTo(file)
    }

    /** Memory and disk together — the pending share is one record with one state. */
    private fun dropPending() {
        deleteRecord(PENDING_FILE)
        _pending.value = null
    }

    private fun deleteRecord(name: String) {
        File(dir, name).delete()
        File(dir, "$name.tmp").delete()
    }

    private fun conversationDir(conversationId: String): File = File(dir, "conv_$conversationId")

    /**
     * Attachment files are the numbered ones and nothing else — the per-
     * conversation record also holds F16's auto-send marker and notice, and a
     * renumbering pass that treated those as attachments would rename them into
     * the attachment list.
     */
    private fun attachmentFiles(convDir: File): List<File> = convDir.listFiles().orEmpty()
        .filter { it.name.matches(Regex("\\d+\\.txt")) }
        .sortedBy { it.nameWithoutExtension.toIntOrNull() }

    companion object {
        const val PENDING_FILE = "pending.json"
        const val SUMMARIZE_FILE = "summarize.json"
        const val AUTOSEND_FILE = "autosend"
        const val NOTICE_FILE = "notice.txt"

        /** Shown on the thread when the tools PUT failed and the message stayed staged. */
        const val TOOLS_NOT_ENABLED_NOTICE =
            "The summarize tools could not be enabled, so nothing was sent — a summary without " +
            "the fetch tool would be invented. Press Send to answer without them, or retry in " +
            "the tools sheet."

        val json = Json
    }
}
