package com.hpz.llmdockchat.feature.share

import java.io.File
import java.nio.file.Files
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

private const val TEXT = "shared body"
private const val IMAGE_DATA = "data:image/jpeg;base64,AAAA"
private const val IMAGE_URI = "content://media/pic"
private const val FILE_URI = "content://file/provider"

/** A reader the test steers: names, inline text and images per Uri, with optional stalls and failures. */
private class FakeReader(
    val names: Map<String, String> = emptyMap(),
    val texts: Map<String, String> = emptyMap(),
    val images: Map<String, String> = emptyMap(),
    val readBlock: (() -> Unit)? = null,
    val fails: Boolean = false,
) : SharedContentReader {
    var readCalls = 0
    val readThreads = mutableListOf<Thread>()

    override fun displayName(uri: String): String? = names[uri]

    override fun readInlineText(uri: String): String? {
        enter()
        return texts[uri]
    }

    override fun readImageAttachment(uri: String): String? {
        enter()
        return images[uri]
    }

    private fun enter() {
        if (fails) throw IllegalStateException("provider is dead")
        readCalls += 1
        readThreads.add(Thread.currentThread())
        readBlock?.invoke()
    }
}

private val IMAGE = ShareRequest(
    action = "android.intent.action.SEND",
    mimeType = "image/png",
    streamUri = IMAGE_URI,
)

private val FILE = ShareRequest(
    action = "android.intent.action.SEND",
    mimeType = "text/plain",
    streamUri = FILE_URI,
    streamHint = "notes.txt",
)

private val TEXT_ONLY = ShareRequest(
    action = "android.intent.action.SEND",
    mimeType = "text/plain",
    text = TEXT,
)

private fun dir(): File = Files.createTempDirectory("share-import").toFile()

private fun eagerScope() = CoroutineScope(UnconfinedTestDispatcher())

private fun eagerStore() = SharedDraftStore(dir(), eagerScope())

class ShareImportTest {
    // -- the decision needs no provider ---------------------------------

    @Test
    fun `a text share is planned as immediate, with no provider read`() {
        val plan = ShareImport.plan(TEXT_ONLY)

        assertTrue(plan is ShareImportPlan.Immediate)
        assertEquals(TEXT, (plan as ShareImportPlan.Immediate).share.text)
    }

    @Test
    fun `a stream-backed share is deferred`() {
        assertTrue(ShareImport.plan(IMAGE) is ShareImportPlan.Deferred)
        assertTrue(ShareImport.plan(FILE) is ShareImportPlan.Deferred)
    }

    @Test
    fun `an unsupported stream is refused on the spot`() {
        val plan = ShareImport.plan(
            ShareRequest(action = "android.intent.action.SEND", mimeType = "video/mp4", streamUri = "content://v"),
        )

        assertTrue(plan is ShareImportPlan.Immediate)
        assertNotNull((plan as ShareImportPlan.Immediate).share.error)
    }

    // -- resolving a deferred share ------------------------------------

    @Test
    fun `a deferred image resolves to the encoded attachment`() = runTest {
        val reader = FakeReader(images = mapOf(IMAGE_URI to IMAGE_DATA))

        val share = ShareImport.resolve(IMAGE, reader, Dispatchers.Unconfined)

        assertEquals(listOf(IMAGE_DATA), share.attachments)
        assertNull(share.error)
    }

    /**
     * The fence label is what the user reads as "this is my file", and a
     * `content://` path segment is usually an opaque id — so the provider's own
     * name wins, with the Uri segment only as a fallback.
     */
    @Test
    fun `the inline fence is labelled with the provider name, falling back to the uri hint`() = runTest {
        val named = ShareImport.resolve(
            FILE,
            FakeReader(names = mapOf(FILE_URI to "real.txt"), texts = mapOf(FILE_URI to "file body")),
            Dispatchers.Unconfined,
        )
        assertTrue(named.text, named.text.contains("`real.txt`"))
        assertTrue(named.text.contains("file body"))

        val hinted = ShareImport.resolve(
            FILE,
            FakeReader(texts = mapOf(FILE_URI to "file body")),
            Dispatchers.Unconfined,
        )
        assertTrue(hinted.text, hinted.text.contains("`notes.txt`"))
    }

    /**
     * A throw out of the provider has to end up as the typed failure for the
     * content the user actually shared; otherwise the picker sits on a "reading"
     * placeholder forever, which is worse than an error row.
     */
    @Test
    fun `a provider that throws becomes the typed failure instead of a crash`() = runTest {
        val broken = FakeReader(fails = true)

        assertEquals(
            ShareImport.IMAGE_UNREADABLE,
            ShareImport.resolve(IMAGE, broken, Dispatchers.Unconfined).error,
        )
        assertEquals(
            ShareImport.FILE_UNREADABLE,
            ShareImport.resolve(FILE, broken, Dispatchers.Unconfined).error,
        )
    }

    // -- the coordinator: ordering, and where the read runs -------------

    @Test
    fun `a text share is staged on the spot and claims its delivery`() {
        val store = eagerStore()

        ShareIntakeCoordinator(eagerScope(), FakeReader(), store, Dispatchers.Unconfined).submit("tok-1", TEXT_ONLY)

        assertEquals(TEXT, store.pending.value?.text)
        assertEquals("tok-1", store.handledToken)
    }

    @Test
    fun `a slow read that lands after a newer share does not resurrect the old one`() = runTest {
        val reader = FakeReader(images = mapOf(IMAGE_URI to IMAGE_DATA))
        val store = SharedDraftStore(dir())
        // Both the import's launch and its read sit on a scheduler the test drives, so
        // "still in flight" is a fact of the scheduler rather than a timing guess.
        val schedulerScope = CoroutineScope(StandardTestDispatcher(testScheduler))
        val coordinator = ShareIntakeCoordinator(
            schedulerScope,
            reader,
            store,
            StandardTestDispatcher(testScheduler),
        )

        coordinator.submit("tok-a", IMAGE)
        assertEquals("the picker shows a placeholder while the provider is read", true, store.pending.value?.importing)
        assertNull("the placeholder is not a record", SharedDraftStore(dir()).pending.value)

        coordinator.submit("tok-b", TEXT_ONLY)
        advanceUntilIdle()

        assertEquals(1, reader.readCalls)
        assertEquals("a late image must not come back under the newer token", TEXT, store.pending.value?.text)
        assertEquals(emptyList<String>(), store.pending.value?.attachments)
    }

    /**
     * Off the main thread is the whole point: the thread that received the intent
     * may not be the one that asks a provider for bytes.
     */
    @Test
    fun `the read does not run on the thread that submitted the share`() = runTest {
        val reading = CountDownLatch(1)
        val reader = FakeReader(images = mapOf(IMAGE_URI to IMAGE_DATA), readBlock = { reading.countDown() })

        ShareIntakeCoordinator(eagerScope(), reader, eagerStore(), Dispatchers.IO).submit("tok", IMAGE)

        assertTrue("the read never started", reading.await(5, TimeUnit.SECONDS))
        assertTrue(
            "the read ran on ${reader.readThreads.first().name}, the submitting thread",
            reader.readThreads.first() != Thread.currentThread(),
        )
    }

    @Test
    fun `a resolved import replaces the placeholder and reaches disk`() = runTest {
        val dir = dir()
        val store = SharedDraftStore(dir, eagerScope())

        ShareIntakeCoordinator(eagerScope(), FakeReader(images = mapOf(IMAGE_URI to IMAGE_DATA)), store, Dispatchers.Unconfined)
            .submit("tok", IMAGE)
        store.awaitPendingWrites()

        assertEquals(listOf(IMAGE_DATA), store.pending.value?.attachments)
        assertEquals(listOf(IMAGE_DATA), SharedDraftStore(dir).pending.value?.attachments)
    }

    /**
     * An import that outlives its scope must not corrupt the record: the write
     * never lands, and the disk still describes the share that was there before
     * the placeholder.
     */
    @Test
    fun `an import whose scope is gone leaves the on-disk share standing`() = runTest {
        val dir = dir()
        val scope = eagerScope()
        val store = SharedDraftStore(dir, scope)
        store.stage(StagedShare(text = TEXT), "tok")
        scope.cancel()

        val reader = FakeReader(images = mapOf(IMAGE_URI to IMAGE_DATA))
        store.beginImport()
        store.finishImport(ShareImport.resolve(IMAGE, reader, Dispatchers.Unconfined))

        assertEquals(TEXT, SharedDraftStore(dir).pending.value?.text)
    }
}
