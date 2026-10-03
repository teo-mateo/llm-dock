package com.hpz.llmdockchat.feature.share

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import com.hpz.llmdockchat.feature.thread.readImage
import com.hpz.llmdockchat.feature.thread.toDataUrl
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
    /** `EXTRA_STREAM` as a string; [SharedContentReader] re-parses it. */
    val streamUri: String? = null,
    /**
     * `Uri.lastPathSegment`, available without a provider query. A name hint for
     * nothing but the placeholder's refusal message — content URIs usually end
     * in an opaque id, so the authoritative name always comes from
     * [SharedContentReader.displayName].
     */
    val streamHint: String? = null,
) {
    val hasStream: Boolean get() = streamUri != null

    fun streamName(fallback: String): String =
        streamHint?.substringAfterLast('/').takeUnless { it.isNullOrBlank() } ?: fallback
}

/**
 * The provider I/O a share needs. Every method may block for as long as the
 * provider takes — a cloud-backed document can stall for seconds — which is why
 * none of them is called from the main thread.
 */
interface SharedContentReader {
    fun displayName(uri: String): String?

    /** The stream's start, decoded as UTF-8 and capped at [SharedKindParser.MAX_INLINE_BYTES]. */
    fun readInlineText(uri: String): String?

    /** The image as a downscaled `data:image/jpeg;base64,…` URL, or null if it could not be read. */
    fun readImageAttachment(uri: String): String?
}

/** The production reader: one `ContentResolver`, three blocking reads. */
class ContentResolverShareReader(private val resolver: ContentResolver) : SharedContentReader {

    override fun displayName(uri: String): String? = runCatching {
        resolver.query(
            Uri.parse(uri),
            arrayOf(OpenableColumns.DISPLAY_NAME),
            null,
            null,
            null,
        )?.use { cursor -> if (cursor.moveToFirst()) cursor.getString(0) else null }
    }.getOrNull()

    override fun readInlineText(uri: String): String? = runCatching {
        resolver.openInputStream(Uri.parse(uri))?.use(::readCapped)
    }.getOrNull()

    override fun readImageAttachment(uri: String): String? =
        runCatching { readImage(resolver, Uri.parse(uri))?.toDataUrl() }.getOrNull()

    /** Bounded read — a huge file is truncated at the inline cap, not loaded whole. */
    private fun readCapped(stream: java.io.InputStream): String {
        val max = SharedKindParser.MAX_INLINE_BYTES
        val buffer = ByteArray(max + 1)
        var total = 0
        while (total <= max) {
            val n = stream.read(buffer, total, max + 1 - total)
            if (n < 0) break
            total += n
        }
        return String(buffer, 0, minOf(total, max), Charsets.UTF_8)
    }
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
    const val IMAGE_UNREADABLE = "That image could not be read."
    const val PHOTO_UNREADABLE = "That photo could not be read."
    const val FILE_UNREADABLE = "That file could not be read."

    fun plan(request: ShareRequest): ShareImportPlan {
        if (SharedKindParser.readFor(request.action, request.mimeType, request.text, request.hasStream) !=
            SharedRead.None
        ) {
            return ShareImportPlan.Deferred
        }
        return ShareImportPlan.Immediate(shareFor(request))
    }

    /** Reads and encodes. Never throws: a failed read is the share that says so. */
    suspend fun resolve(request: ShareRequest, reader: SharedContentReader, io: CoroutineDispatcher): StagedShare =
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
                // The provider's name reclassified the share — a `content://` stream
                // whose display name is a PDF, say. The verdict is the classifier's.
                else -> shareOf(classify(request, request.hasStream, name))
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
        // A stream-backed share whose bytes have not been read yet: empty, and says so.
        else -> StagedShare(importing = true)
    }

    private const val FALLBACK_NAME = "file.txt"
}

/**
 * Stages deliveries as they arrive, on the calling thread, and reads their
 * content on [scope].
 *
 * The token is claimed before anything is read: a read can stall or throw, and a
 * served delivery must stay served whatever the read did. `currentToken` is what
 * makes the second of two shares win — an import that finishes out of order
 * finds its token no longer current and drops its own result rather than
 * overwriting what the user shared last.
 */
class ShareIntakeCoordinator(
    private val scope: CoroutineScope,
    private val reader: SharedContentReader,
    private val store: SharedDraftStore,
    private val io: CoroutineDispatcher,
) {

    private var currentToken: String? = null

    fun submit(token: String, request: ShareRequest) {
        currentToken = token
        store.rememberHandled(token)
        when (val plan = ShareImport.plan(request)) {
            is ShareImportPlan.Immediate -> store.stage(plan.share)
            ShareImportPlan.Deferred -> {
                store.beginImport()
                scope.launch {
                    val share = ShareImport.resolve(request, reader, io)
                    if (currentToken == token) store.finishImport(share)
                }
            }
        }
    }
}
