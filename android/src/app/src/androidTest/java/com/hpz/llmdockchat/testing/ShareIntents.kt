package com.hpz.llmdockchat.testing

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.provider.MediaStore
import com.hpz.llmdockchat.MainActivity
import com.hpz.llmdockchat.feature.share.ShareDeliveryToken
import java.io.ByteArrayOutputStream

/**
 * Real share `Intent`s for the instrumented intake tests — they live in
 * `androidTest` because unit tests only get the throwing android.jar stubs.
 * The image goes through MediaStore (the shape `dev.sh share-image` uses), so
 * the activity receives a genuine `content://` grant, not a file path.
 */
object ShareIntents {

    fun textShare(context: Context, text: String): Intent =
        shareIntent(context).apply { putExtra(Intent.EXTRA_TEXT, text) }

    fun imageShare(context: Context, label: String): Pair<Uri, Intent> {
        val png = ByteArrayOutputStream()
        Bitmap.createBitmap(16, 16, Bitmap.Config.ARGB_8888)
            .compress(Bitmap.CompressFormat.PNG, 100, png)
        val uri = context.contentResolver.insert(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, "$label.png")
                put(MediaStore.MediaColumns.MIME_TYPE, "image/png")
            },
        ) ?: error("MediaStore insert failed for $label")
        context.contentResolver.openOutputStream(uri)?.use { it.write(png.toByteArray()) }
        return uri to shareIntent(context).apply {
            type = "image/png"
            putExtra(Intent.EXTRA_STREAM, uri)
        }
    }

    fun expectedTextToken(text: String): String = ShareDeliveryToken.of(
        action = Intent.ACTION_SEND,
        mimeType = "text/plain",
        text = text,
        streamUri = null,
        title = null,
        subject = null,
    )

    private fun shareIntent(context: Context): Intent =
        Intent(Intent.ACTION_SEND).apply {
            setClass(context, MainActivity::class.java)
            type = "text/plain"
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
}
