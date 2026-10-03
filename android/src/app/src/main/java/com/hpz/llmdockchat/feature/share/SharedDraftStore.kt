package com.hpz.llmdockchat.feature.share

import com.hpz.llmdockchat.core.prefs.DraftStore
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json
import java.io.File

/**
 * Where a share lives between the intent and the send. Three records:
 *
 * - **The pending share** — unassigned, staged at intent time and shown on
 *   the target picker. Survives navigation, the Connect round trip, and
 *   process death: the record is a JSON file in [dir] and the
 *   in-memory [pending] is hydrated from it at construction.
 * - **Per-conversation attachments** — written when the user picks a target
 *   ([reassign]), read back by the thread's `load()` so a force-stop between
 *   the pick and the send does not lose the staged image. One file
 *   per attachment, named `0.txt`, `1.txt`…, so removing one renumbers the
 *   rest and the record stays index-aligned with the composer's list.
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
) {

    private val _pending = MutableStateFlow<StagedShare?>(readPending())
    val pending: StateFlow<StagedShare?> = _pending.asStateFlow()

    private val _handled = MutableStateFlow(readHandledToken())

    private val writes = Channel<suspend () -> Unit>(Channel.UNLIMITED)

    private var importToken: String? = null

    /**
     * Serialises a pending-record transition with the disk write that backs it.
     * The write queue is FIFO, so without this memory can settle in one order and
     * `pending.json` in another: a dismissal that won the race in memory can still
     * be followed on disk by the write it displaced, and the share the user threw
     * away returns after a restart.
     */
    private val pendingCommit = Any()

    init {
        scope.launch {
            for (write in writes) runCatching { write() }
        }
    }

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
     * The picker's "pick a conversation" and the new-chat flow's
     * `onConversationCreated` both land here: the staged text becomes the
     * conversation's draft (the thread's `loadedFrom` already merges it), the
     * attachments move to the per-conversation record, and the pending share
     * is gone.
     */
    fun reassign(conversationId: String, drafts: DraftStore) {
        val share = _pending.value ?: return
        // A placeholder is not content: spending it would hand the user an empty
        // composer and throw the incoming bytes away.
        if (share.importing) return
        if (share.text.isNotBlank()) drafts.save(conversationId, share.text)
        saveAttachments(conversationId, share.attachments)
        clearPending()
    }

    /**
     * The summarize claim: one prepared user turn owed to one
     * conversation, written before the thread opens and consumed by its first
     * `load()`. A sibling of [PENDING_FILE] rather than a child of the
     * conversation directory, because [saveAttachments] wipes that directory —
     * a claim filed there would be erased by the attachment write that
     * follows it, cancelling the action the user just took.
     */
    fun stageForAutoSend(conversationId: String, message: String) {
        enqueue {
            dir.mkdirs()
            val file = autoSendFile(conversationId)
            val tmp = File(dir, "${file.name}.tmp")
            tmp.writeText(message)
            tmp.renameTo(file)
        }
        clearPending()
    }

    /** Reads the claim and spends it, so no second visit can send it again. */
    suspend fun takeAutoSend(conversationId: String): String? = drain {
        val file = autoSendFile(conversationId)
        if (!file.exists()) return@drain null
        val message = runCatching { file.readText() }.getOrNull()
        file.delete()
        message?.takeIf { it.isNotBlank() }
    }

    fun saveAttachments(conversationId: String, attachments: List<String>) {
        if (attachments.isEmpty()) return
        enqueue {
            val convDir = conversationDir(conversationId).apply { mkdirs() }
            convDir.listFiles().orEmpty().forEach { it.delete() }
            attachments.forEachIndexed { index, dataUrl ->
                File(convDir, "$index.txt").writeText(dataUrl)
            }
        }
    }

    /** Read back the staged attachments for a conversation. */
    suspend fun attachments(conversationId: String): List<String> = drain {
        val files = conversationDir(conversationId).listFiles().orEmpty()
            .sortedBy { it.nameWithoutExtension.toIntOrNull() }
        files.mapNotNull { file -> file.readText().takeIf { it.isNotEmpty() } }
    }

    /**
     * The composer's remove button keeps the record aligned with the on-screen
     * list — the file for that index is deleted and the rest renumbered, so a
     * later re-entry cannot resurrect a removed attachment — no ghosts.
     */
    fun removeAttachment(conversationId: String, index: Int) {
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
    fun clear(conversationId: String) {
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
        writes.trySend(write)
    }

    /**
     * Runs [op] on the write queue, after everything enqueued before this call:
     * a reader must not see a state older than the write it is answering for.
     */
    private suspend fun <T> drain(op: suspend () -> T): T {
        val done = CompletableDeferred<T>()
        writes.send {
            try {
                done.complete(op())
            } catch (failure: Throwable) {
                done.completeExceptionally(failure)
                throw failure
            }
        }
        return done.await()
    }

    /** Returns once every write enqueued before this call has reached disk. */
    internal suspend fun awaitPendingWrites() = drain { Unit }

    private companion object {
        const val PENDING_FILE = "pending.json"
        const val HANDLED_FILE = "handled.json"
        val json = Json
    }
}
