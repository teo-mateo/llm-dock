package com.hpz.llmdockchat.core.attachment

import android.content.Context
import android.net.Uri
import androidx.core.content.FileProvider
import java.io.File

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
