package com.hpz.llmdockchat.feature.thread

import android.content.ContentResolver
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.util.Base64
import androidx.core.content.FileProvider
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Images on the wire are `data:image/jpeg;base64,…` URLs — the same encoding
 * the web composer sends (`ChatInput.jsx` posts `images` as data URLs), so a
 * photo attached on the phone renders on the desktop and vice versa.
 */
private const val DATA_URL_PREFIX = "data:"
private const val BASE64_MARKER = ";base64,"

/**
 * A photo straight off a modern phone camera is several thousand pixels wide
 * and multiple megabytes; base64 inflates it by a third again, and it all goes
 * into a JSON body and then into a SQLite row. Downscaling first is what makes
 * F04-R9's "a large photo is downscaled rather than failing" true.
 */
const val MAX_ATTACHMENT_EDGE_PX = 1568
private const val JPEG_QUALITY = 85

fun Bitmap.toDataUrl(): String {
    val scaled = downscaled(MAX_ATTACHMENT_EDGE_PX)
    val bytes = ByteArrayOutputStream().use { out ->
        scaled.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
        out.toByteArray()
    }
    return "${DATA_URL_PREFIX}image/jpeg$BASE64_MARKER${Base64.encodeToString(bytes, Base64.NO_WRAP)}"
}

/**
 * Decodes with `inSampleSize` so a 12-megapixel original is never fully
 * materialised — the full-size decode is what actually OOMs on a phone, not the
 * scaling that follows it.
 */
fun readImage(resolver: ContentResolver, uri: Uri): Bitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    // A bounds-only decode returns null by design, so the stream itself is what
    // gets null-checked here — testing the decode result would reject every
    // image ever picked.
    val boundsStream = resolver.openInputStream(uri) ?: return null
    boundsStream.use { BitmapFactory.decodeStream(it, null, bounds) }
    if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null

    val options = BitmapFactory.Options().apply {
        inSampleSize = sampleSizeFor(bounds.outWidth, bounds.outHeight, MAX_ATTACHMENT_EDGE_PX)
    }
    return resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, options) }
}

/**
 * Somewhere for the camera app to write a full-resolution capture, handed over
 * as a `content://` Uri through the app's [FileProvider] (`camera-captures` in
 * `res/xml/file_paths.xml`). Cache-dir, because the file is only ever read once
 * — the attachment itself lives on as a downscaled data URL.
 */
fun newCaptureUri(context: Context): Uri {
    val dir = File(context.cacheDir, CAPTURE_DIR).apply { mkdirs() }
    val file = File.createTempFile("capture_", ".jpg", dir)
    return FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
}

/** Best-effort: a capture left behind is cache, and the OS will reclaim it. */
fun discardCapture(context: Context, uri: Uri) {
    runCatching { context.contentResolver.delete(uri, null, null) }
}

private const val CAPTURE_DIR = "camera-captures"

fun decodeDataUrl(dataUrl: String): Bitmap? {
    val encoded = dataUrl.substringAfter(BASE64_MARKER, "").takeIf { it.isNotEmpty() } ?: return null
    return runCatching {
        val bytes = Base64.decode(encoded, Base64.DEFAULT)
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }.getOrNull()
}

internal fun sampleSizeFor(width: Int, height: Int, maxEdge: Int): Int {
    var sample = 1
    var longest = maxOf(width, height)
    while (longest / 2 >= maxEdge) {
        longest /= 2
        sample *= 2
    }
    return sample
}

private fun Bitmap.downscaled(maxEdge: Int): Bitmap {
    val longest = maxOf(width, height)
    if (longest <= maxEdge) return this
    val ratio = maxEdge.toFloat() / longest
    return Bitmap.createScaledBitmap(this, (width * ratio).toInt(), (height * ratio).toInt(), true)
}
