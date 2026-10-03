package com.hpz.llmdockchat.feature.thread

import com.hpz.llmdockchat.feature.share.SharedContentReader
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.withContext

/**
 * Turns a picked or captured `content://` image into an attachment away from the
 * main thread. Provider open, bounds decode, sampled decode, downscale, JPEG
 * compress and base64 all scale with the photo — several hundred milliseconds on
 * a camera-sized original — and a gallery pick is exactly the moment the
 * composer has to stay responsive.
 */
class AttachmentImporter(
    private val reader: SharedContentReader,
    private val io: CoroutineDispatcher,
) {
    /** Null means the image could not be read; the caller owns the message. */
    suspend fun import(uri: String): String? = withContext(io) { reader.readImageAttachment(uri) }
}
