package com.hpz.llmdockchat.core.attachment

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns

/** Cap per-file inlined text — the web's `MAX_INLINE_BYTES` (`ChatInput.jsx`). */
const val MAX_INLINE_BYTES = 512 * 1024

/**
 * The provider I/O a share needs. Every method may block for as long as the
 * provider takes — a cloud-backed document can stall for seconds — which is why
 * none of them is called from the main thread.
 */
interface AttachmentReader {
    fun displayName(uri: String): String?

    /** The stream's start, decoded as UTF-8 and capped at [MAX_INLINE_BYTES]. */
    fun readInlineText(uri: String): String?

    /** The image as a downscaled `data:image/jpeg;base64,…` URL, or null if it could not be read. */
    fun readImageAttachment(uri: String): String?
}

/** The production reader: one `ContentResolver`, three blocking reads. */
class ContentResolverAttachmentReader(private val resolver: ContentResolver) : AttachmentReader {

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
        val max = MAX_INLINE_BYTES
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
