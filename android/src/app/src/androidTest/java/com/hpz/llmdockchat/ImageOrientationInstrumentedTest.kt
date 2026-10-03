package com.hpz.llmdockchat

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.media.ExifInterface
import android.net.Uri
import androidx.core.content.FileProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.hpz.llmdockchat.feature.share.ContentResolverShareReader
import com.hpz.llmdockchat.feature.thread.MAX_ATTACHMENT_EDGE_PX
import com.hpz.llmdockchat.feature.thread.decodeDataUrl
import com.hpz.llmdockchat.feature.thread.readImage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Orientation is the one property of an attached photo that survives nothing:
 * `toDataUrl` re-encodes and drops the metadata, so the pixels handed to the
 * vision model have to be upright already. Every fixture here is asymmetric on
 * purpose — four distinct quadrant colours on a non-square source — because width
 * and height alone cannot tell a rotation from a mirror, which is most of what
 * this pipeline gets wrong when it is wrong.
 *
 * Fixtures go under `cacheDir/camera-captures/` and are read back through the
 * app's own `FileProvider`, so the Uri under test has the `content://` shape the
 * picker, the camera and the share sheet all hand over.
 */
@RunWith(AndroidJUnit4::class)
class ImageOrientationInstrumentedTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val resolver get() = context.contentResolver

    private val storedWidth = 64
    private val storedHeight = 128

    @Test
    fun everyExifOrientationDecodesUpright() {
        EXPECTED.forEach { (tag, expected) ->
            val uri = writeQuadrantFixture("oriented_$tag.jpg", tag)
            val decoded = readImage(resolver, uri)
            assertNotNull("orientation $tag decoded", decoded)
            val bitmap = decoded!!
            assertEquals("orientation $tag width", expected.width, bitmap.width)
            assertEquals("orientation $tag height", expected.height, bitmap.height)
            assertEquals("orientation $tag quadrants", expected.quadrants, bitmap.quadrants())
        }
    }

    @Test
    fun orientationUndefinedDecodesAsStored() {
        val uri = writeQuadrantFixture("orientation_undefined.jpg", "0")
        val bitmap = readImage(resolver, uri)!!
        assertEquals(storedWidth, bitmap.width)
        assertEquals(storedHeight, bitmap.height)
        assertEquals(listOf("red", "green", "blue", "black"), bitmap.quadrants())
    }

    @Test
    fun missingExifDecodesAsStored() {
        val uri = writeQuadrantFixture("no_exif.jpg", null)
        val bitmap = readImage(resolver, uri)!!
        assertEquals(storedWidth, bitmap.width)
        assertEquals(storedHeight, bitmap.height)
        assertEquals(listOf("red", "green", "blue", "black"), bitmap.quadrants())
    }

    @Test
    fun theEncodedAttachmentCarriesNoOrientationAndStillLooksUpright() {
        val uri = writeQuadrantFixture("oriented_6.jpg", "6")
        val bitmap = readImage(resolver, uri)!!
        val dataUrl = ContentResolverShareReader(resolver).readImageAttachment(uri.toString())!!

        val redecoded = decodeDataUrl(dataUrl)!!
        assertEquals(storedHeight, redecoded.width)
        assertEquals(storedWidth, redecoded.height)
        assertEquals(bitmap.quadrants(), redecoded.quadrants())

        val encoded = File(context.cacheDir, "camera-captures/reencoded.jpg")
        encoded.writeBytes(android.util.Base64.decode(dataUrl.substringAfter(";base64,"), android.util.Base64.DEFAULT))
        val encodedOrientation = ExifInterface(encoded.absolutePath)
            .getAttribute(ExifInterface.TAG_ORIENTATION)
        assertTrue(
            "the attachment must not encode a transform (orientation was $encodedOrientation)",
            encodedOrientation == null || encodedOrientation == "0" || encodedOrientation == "1",
        )
    }

    @Test
    fun aLargeImageIsSampledDuringDecodeAndCappedOnTheWayOut() {
        val file = File(context.cacheDir, "camera-captures/big.jpg")
        val source = Bitmap.createBitmap(4000, 3000, Bitmap.Config.ARGB_8888)
        Canvas(source).drawColor(Color.rgb(10, 20, 30))
        file.outputStream().use { source.compress(Bitmap.CompressFormat.JPEG, 90, it) }
        val uri = uriFor(file)

        val decoded = readImage(resolver, uri)!!
        assertTrue(
            "a 4000x3000 source must be sampled during decode, not materialised (was ${decoded.width}x${decoded.height})",
            maxOf(decoded.width, decoded.height) <= 2000,
        )

        val dataUrl = ContentResolverShareReader(resolver).readImageAttachment(uri.toString())!!
        val encoded = decodeDataUrl(dataUrl)!!
        assertTrue(
            "the encoded attachment must respect the max edge (was ${encoded.width}x${encoded.height})",
            maxOf(encoded.width, encoded.height) <= MAX_ATTACHMENT_EDGE_PX,
        )
    }

    private fun writeQuadrantFixture(name: String, orientationTag: String?): Uri {
        val bitmap = Bitmap.createBitmap(storedWidth, storedHeight, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        fun block(color: Int, left: Int, top: Int) {
            canvas.drawRect(
                left.toFloat(),
                top.toFloat(),
                (left + storedWidth / 2).toFloat(),
                (top + storedHeight / 2).toFloat(),
                Paint().apply { isAntiAlias = false; this.color = color },
            )
        }
        canvas.drawColor(Color.BLACK)
        block(Color.RED, 0, 0)
        block(Color.GREEN, storedWidth / 2, 0)
        block(Color.BLUE, 0, storedHeight / 2)

        val file = File(context.cacheDir, "camera-captures").apply { mkdirs() }
        val fixture = File(file, name)
        fixture.outputStream().use { out -> bitmap.compress(Bitmap.CompressFormat.JPEG, 100, out) }
        orientationTag?.let {
            ExifInterface(fixture.absolutePath).apply {
                setAttribute(ExifInterface.TAG_ORIENTATION, it)
                saveAttributes()
            }
        }
        return uriFor(fixture)
    }

    private fun uriFor(file: File): Uri =
        FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)

    /** Quadrant colours, read at quarter points: top-left, top-right, bottom-left, bottom-right. */
    private fun Bitmap.quadrants(): List<String> {
        val points = listOf(width / 4 to height / 4, width - width / 4 to height / 4, width / 4 to height - height / 4, width - width / 4 to height - height / 4)
        return points.map { (x, y) -> nearest(getPixel(x, y)) }
    }

    private fun nearest(pixel: Int): String {
        val candidates = mapOf(
            "red" to Color.RED,
            "green" to Color.GREEN,
            "blue" to Color.BLUE,
            "black" to Color.BLACK,
            "white" to Color.WHITE,
        )
        return candidates.minByOrNull { (_, c) ->
            val d = listOf(Color.red(pixel) - Color.red(c), Color.green(pixel) - Color.green(c), Color.blue(pixel) - Color.blue(c))
            d.sumOf { it * it }
        }!!.key
    }

    private class Expect(val width: Int, val height: Int, val quadrants: List<String>)

    /**
     * The EXIF display transforms, applied by hand to a source whose stored
     * quadrants are red top-left, green top-right, blue bottom-left, black
     * bottom-right (64x128, non-square so a turn swaps the dimensions). Deriving
     * the expectation from the tag through the platform would let a wrong platform
     * reading pass unnoticed, so the table is written out from the specification
     * instead: 2/4 mirror, 3 turns half, 5/7 mirror along a diagonal, 6 turns
     * clockwise, 8 turns anticlockwise.
     */
    private val EXPECTED = mapOf(
        "1" to Expect(64, 128, listOf("red", "green", "blue", "black")),
        "2" to Expect(64, 128, listOf("green", "red", "black", "blue")),
        "3" to Expect(64, 128, listOf("black", "blue", "green", "red")),
        "4" to Expect(64, 128, listOf("blue", "black", "red", "green")),
        "5" to Expect(128, 64, listOf("red", "blue", "green", "black")),
        "6" to Expect(128, 64, listOf("blue", "red", "black", "green")),
        "7" to Expect(128, 64, listOf("black", "green", "blue", "red")),
        "8" to Expect(128, 64, listOf("green", "black", "red", "blue")),
    )
}
