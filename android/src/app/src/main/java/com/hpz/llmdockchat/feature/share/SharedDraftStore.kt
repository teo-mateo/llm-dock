package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.attachment.AutoSendClaimStore
import com.hpz.llmdockchat.core.attachment.ConversationAttachments
import com.hpz.llmdockchat.core.prefs.DraftStore
import com.hpz.llmdockchat.core.prefs.SerialWriteQueue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json
import java.io.File
import java.io.IOException

/**
 * Where a share lives between the intent and the send. Three records:
 *
 * - **The pending share** — unassigned, staged at intent time and shown on
 *   the target picker. Survives navigation, the Connect round trip, and
 *   process death: the record is a JSON file in [dir] and the
 *   in-memory [pending] is hydrated from it at construction.
 * - **Per-conversation attachments** — appended when the user picks a target
 *   ([reassign]), read back by the thread's `load()` so a force-stop between
 *   the pick and the send does not lose the staged image. One file
 *   per attachment, named `0.txt`, `1.txt`…, so removing one renumbers the
 *   rest and the record stays index-aligned with the composer's list, and so a
 *   second share into the same thread adds to the record instead of replacing it.
 * - **The handled token** — the delivery identity of the share this task most
 *   recently claimed, in `handled.json` ([stage] with a token).
 *   [clearPending], [reassign] and [clear] deliberately do not clear it: the
 *   claim must outlive the record it refers to, so a redelivery of an already
 *   served intent is refused at intake instead of re-staging a consumed share.
 *
 * [dir] is the app's `cacheDir/shared-drafts` — cache, so the OS may reclaim
 * it, and never backed up. The text half of a share goes through
 * [DraftStore] (existing per-conversation drafts); only attachments live
 * here.
 *
 * Every write is queued on [scope] and applied in call order, the
 * [com.hpz.llmdockchat.core.prefs.ValuePreference] arrangement: the in-memory
 * flow updates synchronously so the UI never waits on a file, and the disk write
 * happens later, on I/O, without the ordering hazard that an unordered write
 * brings (`clearPending` immediately followed by `stage` must not resurrect a
 * share). [drain] is how a reader asks for "everything I enqueued has reached
 * disk", which is what makes a pick-then-open round trip behave.
 */
class SharedDraftStore(
    private val dir: File,
    scope: CoroutineScope = CoroutineScope(Dispatchers.Unconfined),
) : ConversationAttachments, AutoSendClaimStore {

    private val _pending = MutableStateFlow<StagedShare?>(readPending())
    val pending: StateFlow<StagedShare?> = _pending.asStateFlow()

    private val _handled = MutableStateFlow(readHandledToken())

    private val writes = SerialWriteQueue(scope)

    private var importToken: String? = null

    /**
     * Serialises a pending-record transition with the disk write that backs it.
     * The write queue is FIFO, so without this memory can settle in one order and
     * `pending.json` in another: a dismissal that won the race in memory can still
     * be followed on disk by the write it displaced, and the share the user threw
     * away returns after a restart.
     */
    private val pendingCommit = Any()

    /** The last delivery claimed by intake; a redelivery with this token is refused. */
    val handledToken: String? get() = _handled.value

    /**
     * Called at intent time. [token] claims the delivery before the pending
     * record is queued: the crash window between the two then loses a share (the
     * user re-shares) rather than replaying one, the safe direction for a
     * consume-once flow.
     */
    fun stage(share: StagedShare, token: String? = null) {
        synchronized(pendingCommit) {
            if (token != null) rememberHandled(token)
            _pending.value = share
            enqueue { writePending(share) }
        }
    }

    /** Claims a delivery without staging anything — the [ShareIntake.KeepHydrated] path. */
    fun rememberHandled(token: String) {
        _handled.value = token
        enqueue { writeHandled(token) }
    }

    /**
     * A stream-backed share is being read. In memory only: an import cut short by
     * process death leaves no record, so the user re-shares instead of the picker
     * sitting on "reading" forever. [token] is the delivery the placeholder stands
     * for, which is what [finishImport] has to match.
     */
    fun beginImport(token: String) {
        synchronized(pendingCommit) {
            importToken = token
            _pending.value = StagedShare(importing = true)
        }
    }

    /**
     * Replaces the [beginImport] placeholder of [token]. Anything else that has
     * happened to the pending share in the meantime — dismissed, consumed by a
     * pick, superseded by a newer delivery — wins, and this import's content is
     * dropped rather than resurrected.
     *
     * The apply happens under [pendingCommit]: the reader of this share runs on
     * I/O while the picker's Close button runs on the main thread, and a share the
     * user threw away has to stay thrown away in memory *and* on disk.
     */
    fun finishImport(token: String, share: StagedShare) {
        synchronized(pendingCommit) {
            if (importToken != token) return
            val current = _pending.value ?: return
            if (!current.importing) return
            _pending.value = share
            importToken = null
            enqueue { writePending(share) }
        }
    }

    /** Dismissing the picker, or a share already consumed by a pick. */
    fun clearPending() {
        synchronized(pendingCommit) {
            _pending.value = null
            enqueue { deletePending() }
        }
    }

    /**
     * Spends [share] only if it is still the staged one. A share staged while a
     * pick was writing is a different record and must survive: the pick filed
     * the one it captured, not this one.
     */
    private fun clearPendingIf(share: StagedShare) {
        synchronized(pendingCommit) {
            if (_pending.value !== share) return
            _pending.value = null
            enqueue { deletePending() }
        }
    }

    /**
     * The picker's "pick a conversation" and the new-chat flow's
     * `onConversationCreated` both land here: the staged text is **appended** to
     * the conversation's draft ([mergedDraft]) rather than replacing it, the
     * attachments are appended to the per-conversation record, and the pending
     * share is gone only once both writes have reached disk.
     *
     * Suspending for two reasons: the existing draft cannot be read from memory
     * before DataStore has hydrated (a share that starts the process cold would
     * otherwise read "no draft" and overwrite one), and the destination writes
     * have to be durable before the pending record is spent. A failure anywhere
     * in here is returned instead of thrown, and leaves the share on the picker
     * rather than losing it.
     */
    suspend fun reassign(conversationId: String, drafts: DraftStore): Result<Unit> {
        val share = _pending.value ?: return Result.success(Unit)
        // A placeholder is not content: spending it would hand the user an empty
        // composer and throw the incoming bytes away.
        if (share.importing) return Result.success(Unit)
        // Not cancellable: a caller that navigates away after the writes landed
        // must still spend the record, or a re-pick appends the attachments a
        // second time.
        return withContext(NonCancellable) {
            if (share.text.isNotBlank()) {
                val merged = mergedDraft(drafts.draft(conversationId), share.text)
                drafts.saveConfirmed(conversationId, merged).onFailure { return@withContext Result.failure(it) }
            }
            appendAttachments(conversationId, share.attachments)
                .onFailure { return@withContext Result.failure(it) }
            clearPendingIf(share)
            Result.success(Unit)
        }
    }

    /**
     * The summarize claim: one prepared user turn owed to one
     * conversation, written before the thread opens and consumed by its first
     * `load()`. A sibling of [PENDING_FILE] rather than a child of the
     * conversation directory, because [appendAttachments] writes numbered files
     * into that directory and [attachments] reads all of them back — a claim
     * filed there would be handed to the composer as a staged image.
     */
    suspend fun stageForAutoSend(conversationId: String, message: String): Result<Unit> {
        val share = _pending.value
        return withContext(NonCancellable) {
            confirmed {
                dir.mkdirs()
                val file = autoSendFile(conversationId)
                val tmp = File(dir, "${file.name}.tmp")
                tmp.writeText(message)
                if (!tmp.renameTo(file)) throw IOException("could not move ${tmp.name} into place")
            }.onSuccess { if (share != null) clearPendingIf(share) }
        }
    }

    /** Reads the claim and spends it, so no second visit can send it again. */
    override suspend fun takeAutoSend(conversationId: String): String? = drain {
        val file = autoSendFile(conversationId)
        if (!file.exists()) return@drain null
        val message = runCatching { file.readText() }.getOrNull()
        file.delete()
        message?.takeIf { it.isNotBlank() }
    }

    /**
     * Adds to the conversation's staged attachments, keeping what is already
     * there: a second share into a thread that already holds an unsent one must
     * not throw the first one away. Indexes continue after the highest existing
     * one, so the record stays index-aligned with the composer's list and
     * [removeAttachment]'s renumbering still holds.
     *
     * All-or-nothing: a write that fails deletes what this call already wrote,
     * so a retry starts at the same index instead of appending a second copy.
     */
    suspend fun appendAttachments(conversationId: String, attachments: List<String>): Result<Unit> {
        if (attachments.isEmpty()) return Result.success(Unit)
        return confirmed {
            val convDir = conversationDir(conversationId)
            if (!convDir.mkdirs() && !convDir.isDirectory) {
                throw IOException("could not create $convDir")
            }
            val next = convDir.listFiles().orEmpty()
                .mapNotNull { file -> file.nameWithoutExtension.toIntOrNull() }
                .maxOrNull()?.plus(1) ?: 0
            val written = mutableListOf<File>()
            try {
                attachments.forEachIndexed { offset, dataUrl ->
                    val file = File(convDir, "${next + offset}.txt")
                    written += file
                    file.writeText(dataUrl)
                }
            } catch (failure: Throwable) {
                written.forEach { it.delete() }
                throw failure
            }
        }
    }

    /** Read back the staged attachments for a conversation. */
    override suspend fun attachments(conversationId: String): List<String> = drain {
        val files = conversationDir(conversationId).listFiles().orEmpty()
            .sortedBy { it.nameWithoutExtension.toIntOrNull() }
        files.mapNotNull { file -> file.readText().takeIf { it.isNotEmpty() } }
    }

    /**
     * The composer's remove button keeps the record aligned with the on-screen
     * list — the file for that index is deleted and the rest renumbered, so a
     * later re-entry cannot resurrect a removed attachment — no ghosts.
     */
    override fun removeAttachment(conversationId: String, index: Int) {
        enqueue {
            val convDir = conversationDir(conversationId)
            if (!convDir.exists()) return@enqueue
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
    }

    /** Send, or leaving the thread — the staged record is spent. */
    override fun clear(conversationId: String) {
        enqueue {
            conversationDir(conversationId).deleteRecursively()
            autoSendFile(conversationId).delete()
        }
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

    private fun enqueue(write: suspend () -> Unit) {
        writes.post(write)
    }

    /**
     * Runs [write] on the queue and waits for *its* result, so a caller that is
     * about to delete the only other copy learns whether the new one landed.
     * A drained queue still means only "nothing is queued".
     */
    private suspend fun <T> confirmed(write: suspend () -> T): Result<T> = writes.confirmed(write)

    /**
     * Runs [op] on the write queue, after everything enqueued before this call:
     * a reader must not see a state older than the write it is answering for.
     */
    private suspend fun <T> drain(op: suspend () -> T): T = writes.confirmed(op).getOrThrow()

    /** Returns once every write enqueued before this call has reached disk. */
    internal suspend fun awaitPendingWrites() = drain { Unit }

    private companion object {
        const val PENDING_FILE = "pending.json"
        const val HANDLED_FILE = "handled.json"
        val json = Json
    }
}

/**
 * The composer text a pick leaves behind: what the user had unsent, with the
 * shared text added after it. The draft goes first because it is what the user
 * wrote and the share is what they then aimed it at; a blank line separates them
 * because a chat message is where these meet, and a bare concatenation would
 * fuse a sentence to a URL.
 *
 * A draft already ending with the shared text is returned untouched — that is
 * the shape of a redelivered share, and duplicating it is the failure this
 * function exists to prevent.
 */
internal fun mergedDraft(existing: String, shared: String): String {
    val incoming = shared.trimEnd()
    if (incoming.isBlank()) return existing
    val current = existing.trimEnd()
    if (current.isBlank()) return incoming
    if (current.endsWith(incoming)) return existing
    return "$current\n\n$incoming"
}

/**
 * Shown when the staged share could not be filed into a conversation. The
 * pending record is untouched, so the same pick can be retried.
 */
internal const val SHARE_SAVE_FAILED =
    "Couldn't save the share to this conversation \u2014 nothing was lost. Try again."
