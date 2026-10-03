package com.hpz.llmdockchat.feature.share

import java.io.File
import java.nio.file.Files
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Issue 278. What a share does before its bytes exist, and what may happen to a
 * read that finishes late, off-thread, or nowhere at all.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ShareImportTest {

    private fun dir(): File = Files.createTempDirectory("shares").toFile().apply { deleteOnExit() }

    private val imageUri = "content://media/pic"
    private val secondImageUri = "content://media/pic2"
    private val fileUri = "content://file/provider"

    private val textOnly = ShareRequest("android.intent.action.SEND", "text/plain", text = "shared text")
    private val image = ShareRequest("android.intent.action.SEND", "image/jpeg", streamUri = imageUri)
    private val secondImage = ShareRequest("android.intent.action.SEND", "image/png", streamUri = secondImageUri)
    private val file = ShareRequest("android.intent.action.SEND", "text/plain", streamUri = fileUri)

    /** A sender that announced a text file and handed over neither text nor stream. */
    private val textWithoutStream = ShareRequest("android.intent.action.SEND", "text/plain")

    private val imageData = "data:image/jpeg;base64,QUJD"
    private val secondImageData = "data:image/png;base64,REVm"

    @Test
    fun `plain text is staged with no read at all`() {
        val reader = FakeReader()

        val plan = ShareImport.plan(textOnly)

        assertTrue(plan is ShareImportPlan.Immediate)
        assertEquals("shared text", (plan as ShareImportPlan.Immediate).share.text)
        assertEquals(0, reader.readCalls)
    }

    @Test
    fun `a stream is deferred even when the mime says text`() {
        assertTrue(ShareImport.plan(file) is ShareImportPlan.Deferred)
    }

    @Test
    fun `a share that wants bytes but carries none fails instead of sticking on reading`() {
        val dir = dir()
        val store = SharedDraftStore(dir)
        val coordinator = ShareIntakeCoordinator(ImmediateScope, FakeReader(), store, Dispatchers.Unconfined)

        coordinator.submit("tok", textWithoutStream)

        assertEquals(ShareImport.FILE_UNREADABLE, store.pending.value?.error)
        assertFalse("the record on disk is the failure, not a stuck placeholder", isStuckPlaceholder(dir))
    }

    @Test
    fun `an unsupported type is refused with no read`() {
        val reader = FakeReader()

        val plan = ShareImport.plan(
            ShareRequest("android.intent.action.SEND", "application/pdf", streamUri = "content://doc"),
        )

        assertTrue(plan is ShareImportPlan.Immediate)
        assertNotNull((plan as ShareImportPlan.Immediate).share.error)
        assertEquals(0, reader.readCalls)
    }

    @Test
    fun `a uri hint cannot talk an image out of being read`() = runBlocking {
        val reader = FakeReader(images = mapOf(imageUri to imageData))

        val share = ShareImport.resolve(image, reader, Dispatchers.Unconfined)

        assertEquals(listOf(imageData), share.attachments)
        assertEquals(1, reader.readCalls)
    }

    @Test
    fun `a provider name reclassifies the share it names`() = runBlocking {
        val reader = FakeReader(texts = mapOf(fileUri to "contents"), names = mapOf(fileUri to "notes.md"))

        val share = ShareImport.resolve(file, reader, Dispatchers.Unconfined)

        assertEquals("**Attached file: `notes.md`**", share.text.lines().first())
    }

    @Test
    fun `a read that fails is the share that says so`() = runBlocking {
        val share = ShareImport.resolve(image, FakeReader(), Dispatchers.Unconfined)

        assertEquals(ShareImport.IMAGE_UNREADABLE, share.error)
    }

    @Test
    fun `a provider that throws is the share that says so`() = runBlocking {
        val reader = FakeReader(images = mapOf(imageUri to imageData), throws = setOf(imageUri))

        assertEquals(ShareImport.IMAGE_UNREADABLE, ShareImport.resolve(image, reader, Dispatchers.Unconfined).error)
    }

    @Test
    fun `a text read that fails says so too`() = runBlocking {
        val reader = FakeReader(texts = mapOf(fileUri to "contents"), throws = setOf(fileUri))

        assertEquals(ShareImport.FILE_UNREADABLE, ShareImport.resolve(file, reader, Dispatchers.Unconfined).error)
    }

    @Test
    fun `a slow read that lands after a newer share does not resurrect the old one`() = runTest {
        val dir = dir()
        val reader = FakeReader(images = mapOf(imageUri to imageData))
        val store = SharedDraftStore(dir)
        // Both the import's launch and its read sit on a scheduler the test drives, so
        // "still in flight" is a fact of the scheduler rather than a timing guess.
        val schedulerScope = CoroutineScope(StandardTestDispatcher(testScheduler))
        val coordinator = ShareIntakeCoordinator(
            schedulerScope,
            reader,
            store,
            StandardTestDispatcher(testScheduler),
        )

        coordinator.submit("tok-a", image)
        assertEquals("the picker shows a placeholder while the provider is read", true, store.pending.value?.importing)
        assertFalse("a placeholder is never a record", isStuckPlaceholder(dir))

        coordinator.submit("tok-b", textOnly)
        advanceUntilIdle()

        assertEquals(1, reader.readCalls)
        assertEquals("the newer share is what the picker shows", "shared text", store.pending.value?.text)
        assertFalse(store.pending.value!!.importing)
    }

    @Test
    fun `an older read that lands while a newer placeholder is staged loses`() {
        val first = CountDownLatch(1)
        val second = CountDownLatch(1)
        val aReadDone = CountDownLatch(1)
        val reader = FakeReader(
            images = mapOf(imageUri to imageData, secondImageUri to secondImageData),
            gates = mapOf(imageUri to first, secondImageUri to second),
            afterRead = { uri -> if (uri == imageUri) aReadDone.countDown() },
        )
        val store = SharedDraftStore(dir())
        val coordinator = ShareIntakeCoordinator(
            CoroutineScope(kotlinx.coroutines.Dispatchers.Default),
            reader,
            store,
            Dispatchers.IO,
        )

        coordinator.submit("tok-a", image)
        coordinator.submit("tok-b", secondImage)

        // A's bytes arrive first, while the staged placeholder stands for B.
        first.countDown()
        assertTrue("A's read never returned", aReadDone.await(5, TimeUnit.SECONDS))
        Thread.sleep(250)
        assertEquals("A must not spend B's placeholder", true, store.pending.value?.importing)

        second.countDown()
        assertTrue("B's content never landed", settle { store.pending.value?.attachments?.isNotEmpty() == true })
        assertEquals(
            "the share the placeholder stands for is the one that lands",
            listOf(secondImageData),
            store.pending.value?.attachments,
        )
    }

    @Test
    fun `the read does not run on the thread that submitted the share`() {
        val release = CountDownLatch(1)
        val reader = FakeReader(images = mapOf(imageUri to imageData), gates = mapOf(imageUri to release))
        val store = SharedDraftStore(dir())
        val coordinator = ShareIntakeCoordinator(ImmediateScope, reader, store, Dispatchers.IO)

        coordinator.submit("tok", image)
        val mainSawPlaceholder = store.pending.value?.importing == true
        release.countDown()

        val deadline = System.currentTimeMillis() + 5_000
        while (store.pending.value?.attachments?.isEmpty() != false && System.currentTimeMillis() < deadline) {
            Thread.sleep(20)
        }

        assertTrue("the picker showed a placeholder while the read ran", mainSawPlaceholder)
        assertEquals(listOf(imageData), store.pending.value?.attachments)
        assertTrue(
            "the read ran off the submitting thread",
            reader.threads.isNotEmpty() && reader.threads.none { it === Thread.currentThread() },
        )
    }

    @Test
    fun `a resolved import reaches disk`() = runBlocking {
        val dir = dir()
        val reader = FakeReader(images = mapOf(imageUri to imageData))
        val store = SharedDraftStore(dir)

        store.beginImport("tok")
        store.finishImport("tok", ShareImport.resolve(image, reader, Dispatchers.Unconfined))
        store.awaitPendingWrites()

        assertEquals(listOf(imageData), SharedDraftStore(dir).pending.value?.attachments)
    }

    /** True when `pending.json` is a share still waiting for bytes that will never arrive. */
    private fun isStuckPlaceholder(dir: File): Boolean =
        File(dir, "pending.json").takeIf { it.exists() }?.readText()?.contains("\"importing\":true") == true

    /** Real time on purpose: the reads run on real providers, not on a test scheduler. */
    private fun settle(probe: () -> Boolean): Boolean {
        val deadline = System.currentTimeMillis() + 5_000
        while (System.currentTimeMillis() < deadline) {
            if (probe()) return true
            Thread.sleep(20)
        }
        return false
    }

    private object ImmediateScope : CoroutineScope {
        override val coroutineContext = Dispatchers.Unconfined
    }

    private class FakeReader(
        val names: Map<String, String> = emptyMap(),
        val texts: Map<String, String> = emptyMap(),
        val images: Map<String, String> = emptyMap(),
        val gates: Map<String, CountDownLatch> = emptyMap(),
        val throws: Set<String> = emptySet(),
        val afterRead: (String) -> Unit = {},
    ) : SharedContentReader {
        var readCalls = 0
        val threads = mutableListOf<Thread>()

        override fun displayName(uri: String): String? = names[uri]

        override fun readInlineText(uri: String): String? = enter(uri) { texts[uri] }

        override fun readImageAttachment(uri: String): String? = enter(uri) { images[uri] }

        private fun enter(uri: String, content: () -> String?): String? {
            readCalls += 1
            threads += Thread.currentThread()
            if (uri in throws) error("provider died mid-read")
            gates[uri]?.let { assertTrue("the provider answered within 5s", it.await(5, TimeUnit.SECONDS)) }
            return content().also { afterRead(uri) }
        }
    }
}
