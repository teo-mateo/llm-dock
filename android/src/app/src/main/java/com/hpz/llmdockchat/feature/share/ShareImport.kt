package com.hpz.llmdockchat.feature.share

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import com.hpz.llmdockchat.core.attachment.AttachmentReader
import com.hpz.llmdockchat.core.attachment.FILE_UNREADABLE
import com.hpz.llmdockchat.core.attachment.IMAGE_UNREADABLE
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * The extras of an `ACTION_SEND` intent, as strings.
 *
 * `Intent` and `Uri` are throwing stubs in the JVM test `android.jar`, so the
 * intent is unpacked once at the activity boundary and every rule downstream —
 * classification, whether a provider read is needed at all, the ordering of
 * competing imports — runs on this.
 */
data class ShareRequest(
    val action: String,
    val mimeType: String?,
    val text: String? = null,
    val title: String? = null,
    val subject: String? = null,
    /** `EXTRA_STREAM` as a string; [AttachmentReader] re-parses it. */
    val streamUri: String? = null,
    /**
     * `Uri.lastPathSegment`, available without a provider query. A name hint for
     * nothing but the placeholder's refusal message — content URIs usually end
     * in an opaque id, so the authoritative name always comes from
     * [AttachmentReader.displayName].
     */
    val streamHint: String? = null,
) {
    val hasStream: Boolean get() = streamUri != null

    fun streamName(fallback: String): String =
        streamHint?.substringAfterLast('/').takeUnless { it.isNullOrBlank() } ?: fallback
}

/** What intake can decide before touching a provider. */
sealed interface ShareImportPlan {
    /** Classifiable from the intent alone — a text share, or a refusal. There is nothing to read. */
    data class Immediate(val share: StagedShare) : ShareImportPlan

    /** Stream-backed: stage a placeholder now and read the content off the calling thread. */
    data object Deferred : ShareImportPlan
}

/**
 * Turns a delivered intent into staged content, off the main thread.
 *
 * The split is what keeps the picker responsive: the *decision* uses only the
 * extras the intent already carries, so a placeholder (or a text share, or a
 * refusal) is on screen before any provider is asked for anything; only the
 * bytes behind `EXTRA_STREAM` are read later, on [io].
 */
object ShareImport {

    fun plan(request: ShareRequest): ShareImportPlan {
        if (SharedKindParser.readFor(request.action, request.mimeType, request.text) != SharedRead.None) {
            return ShareImportPlan.Deferred
        }
        return ShareImportPlan.Immediate(shareFor(request))
    }

    /** Reads and encodes. Never throws: a failed read is the share that says so. */
    suspend fun resolve(request: ShareRequest, reader: AttachmentReader, io: CoroutineDispatcher): StagedShare =
        withContext(io) {
            val uri = request.streamUri ?: return@withContext StagedShare(error = FILE_UNREADABLE)
            val name = attempt { reader.displayName(uri) } ?: request.streamName(FALLBACK_NAME)
            when (val kind = classify(request, hasStream = true, streamName = name)) {
                is SharedKind.Image ->
                    attempt { reader.readImageAttachment(uri) }?.let { StagedShare(attachments = listOf(it)) }
                        ?: StagedShare(error = IMAGE_UNREADABLE)
                is SharedKind.TextFile ->
                    attempt { reader.readInlineText(uri) }?.let {
                        StagedShare(text = SharedInlineFormatter.inlineFile(kind.name, it))
                    } ?: StagedShare(error = FILE_UNREADABLE)
                // A stream whose provider name classifies as neither an image nor
                // inlinable text (a PDF, say) is the classifier's refusal, not a
                // read failure.
                else -> shareOf(kind)
            }
        }

    /**
     * A provider may throw instead of returning null — and an import coroutine
     * that dies mid-read leaves the picker sitting on "reading" with nothing to
     * show, which is worse than the error row this turns it into.
     */
    private fun <T> attempt(read: () -> T?): T? = runCatching(read).getOrNull()

    /** The share a classified request stands for, with no stream content read. */
    private fun shareFor(request: ShareRequest): StagedShare {
        val name = request.streamHint?.substringAfterLast('/').takeUnless { it.isNullOrBlank() } ?: FALLBACK_NAME
        return shareOf(classify(request, request.hasStream, name))
    }

    private fun classify(request: ShareRequest, hasStream: Boolean, streamName: String): SharedKind =
        SharedKindParser.classify(
            action = request.action,
            mimeType = request.mimeType,
            text = request.text,
            title = request.title,
            subject = request.subject,
            hasStream = hasStream,
            streamName = streamName,
        )

    private fun shareOf(kind: SharedKind): StagedShare = when (kind) {
        is SharedKind.Text -> StagedShare(text = kind.text, url = SharedUrlExtractor.firstUrl(kind.text))
        is SharedKind.Unsupported -> StagedShare(error = kind.reason)
        // Only reachable with no stream to read — a share that wants bytes and
        // carries none. [SharedKindParser.readFor] sends every other case to
        // [resolve], which is the only producer of the "reading" placeholder.
        else -> StagedShare(error = FILE_UNREADABLE)
    }

    private const val FALLBACK_NAME = "file.txt"
}

/**
 * Stages deliveries as they arrive, on the calling thread, and reads their
 * content on [scope].
 *
 * The token is claimed before anything is read: a read can stall or throw, and a
 * served delivery must stay served whatever the read did. The store is what makes
 * the second of two shares win — [SharedDraftStore.beginImport] names the
 * delivery whose placeholder is staged, so an import that finishes out of order
 * finds its own placeholder gone and drops its result rather than overwriting
 * what the user shared last.
 */
class ShareIntakeCoordinator(
    private val scope: CoroutineScope,
    private val reader: AttachmentReader,
    private val store: SharedDraftStore,
    private val io: CoroutineDispatcher,
) {

    fun submit(token: String, request: ShareRequest) {
        store.rememberHandled(token)
        when (val plan = ShareImport.plan(request)) {
            is ShareImportPlan.Immediate -> store.stage(plan.share)
            ShareImportPlan.Deferred -> {
                store.beginImport(token)
                scope.launch { store.finishImport(token, ShareImport.resolve(request, reader, io)) }
            }
        }
    }
}
