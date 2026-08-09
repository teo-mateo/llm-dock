package com.hpz.llmdockchat.feature.share

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Classification rules for a share intent (F14-R1/R3). */
class SharedKindParserTest {

    private fun classify(
        action: String = SharedKindParser.ACTION_SEND,
        mimeType: String? = null,
        text: String? = null,
        title: String? = null,
        subject: String? = null,
        hasStream: Boolean = false,
        streamName: String? = null,
    ) = SharedKindParser.classify(action, mimeType, text, title, subject, hasStream, streamName)

    // -- text ---------------------------------------------------------------

    @Test
    fun `text plain with EXTRA_TEXT is composer text`() {
        val kind = classify(mimeType = "text/plain", text = "hello")
        assertEquals(SharedKind.Text("hello"), kind)
    }

    @Test
    fun `a bare link folds EXTRA_TITLE in so it is not sent without context`() {
        val kind = classify(
            mimeType = "text/plain",
            text = "https://example.com/article",
            title = "Example Article",
        )
        assertEquals(SharedKind.Text("https://example.com/article\n\nExample Article"), kind)
    }

    @Test
    fun `a non-link text ignores EXTRA_TITLE`() {
        val kind = classify(mimeType = "text/plain", text = "check this out", title = "ignored")
        assertEquals(SharedKind.Text("check this out"), kind)
    }

    @Test
    fun `text plain with only a stream is a text file`() {
        val kind = classify(mimeType = "text/plain", hasStream = true, streamName = "notes.txt")
        assertEquals(SharedKind.TextFile("notes.txt"), kind)
    }

    // -- images -------------------------------------------------------------

    @Test
    fun `an image mime with a stream is an image attachment`() {
        val kind = classify(mimeType = "image/png", hasStream = true, streamName = "photo.png")
        assertEquals(SharedKind.Image, kind)
    }

    @Test
    fun `an image share ignores EXTRA_TEXT - the picture is what was shared`() {
        val kind = classify(mimeType = "image/jpeg", text = "look at this", hasStream = true)
        assertEquals(SharedKind.Image, kind)
    }

    // -- text files ---------------------------------------------------------

    @Test
    fun `text mime with a stream is a text file`() {
        val kind = classify(mimeType = "text/markdown", hasStream = true, streamName = "readme.md")
        assertEquals(SharedKind.TextFile("readme.md"), kind)
    }

    @Test
    fun `application json is a text file`() {
        val kind = classify(mimeType = "application/json", hasStream = true, streamName = "data.json")
        assertEquals(SharedKind.TextFile("data.json"), kind)
    }

    @Test
    fun `a code mime type is a text file`() {
        val kind = classify(mimeType = "application/x-python", hasStream = true, streamName = "main.py")
        assertEquals(SharedKind.TextFile("main.py"), kind)
    }

    // -- unsupported --------------------------------------------------------

    @Test
    fun `a pdf is unsupported with a readable reason`() {
        val kind = classify(mimeType = "application/pdf", hasStream = true, streamName = "doc.pdf")
        assertTrue(kind is SharedKind.Unsupported)
        assertTrue((kind as SharedKind.Unsupported).reason.contains("PDF"))
    }

    @Test
    fun `a binary file is unsupported`() {
        val kind = classify(mimeType = "application/octet-stream", hasStream = true, streamName = "app.exe")
        assertTrue(kind is SharedKind.Unsupported)
    }

    @Test
    fun `an unknown mime is unsupported`() {
        val kind = classify(mimeType = "application/x-unknown", hasStream = true, streamName = "thing.xyz")
        assertTrue(kind is SharedKind.Unsupported)
    }

    // -- mime-less sniffing -------------------------------------------------

    @Test
    fun `a null mime with an image extension sniffs as an image`() {
        val kind = classify(hasStream = true, streamName = "vacation.jpg")
        assertEquals(SharedKind.Image, kind)
    }

    @Test
    fun `a null mime with a text extension sniffs as a text file`() {
        val kind = classify(hasStream = true, streamName = "notes.txt")
        assertEquals(SharedKind.TextFile("notes.txt"), kind)
    }

    @Test
    fun `a null mime with an unknown extension is unsupported`() {
        val kind = classify(hasStream = true, streamName = "mystery.bin")
        assertTrue(kind is SharedKind.Unsupported)
    }

    // -- action guard -------------------------------------------------------

    @Test
    fun `a non-SEND action is not a share`() {
        val kind = classify(action = "android.intent.action.VIEW", mimeType = "text/plain", text = "hi")
        assertTrue(kind is SharedKind.Unsupported)
    }
}
