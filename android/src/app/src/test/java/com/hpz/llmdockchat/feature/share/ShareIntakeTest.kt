package com.hpz.llmdockchat.feature.share

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The share intake gate: which deliveries are staged, which
 * hydrated records are kept, which redeliveries are refused. Primitives in,
 * no `Intent` — the same android.jar-free arrangement as [SharedKindParserTest]
 * that makes the rules testable at all.
 */
class ShareIntakeTest {

    private fun decide(
        action: String? = SharedKindParser.ACTION_SEND,
        viaNewIntent: Boolean = false,
        marked: Boolean = false,
        launchedFromHistory: Boolean = false,
        hasSavedState: Boolean = false,
        token: String = "a",
        handledToken: String? = null,
    ) = ShareIntakeGate.decide(action, viaNewIntent, marked, launchedFromHistory, hasSavedState, token, handledToken)

    // -- the decision table ---------------------------------------------------

    @Test
    fun `an unmarked cold delivery stages`() {
        assertEquals(ShareIntake.Stage, decide(token = "a", handledToken = null))
    }

    @Test
    fun `a marked intent is refused whichever callback carried it`() {
        assertEquals(
            "rotation redelivers the launch intent through onCreate",
            ShareIntake.IgnoreRedelivery,
            decide(marked = true, viaNewIntent = false, hasSavedState = false, token = "t", handledToken = null),
        )
        assertEquals(
            "Recents re-activation hands the same marked intent to onNewIntent",
            ShareIntake.IgnoreRedelivery,
            decide(marked = true, viaNewIntent = true, token = "t", handledToken = null),
        )
        assertEquals(
            "even with the durable claim gone, the mark alone refuses it",
            ShareIntake.IgnoreRedelivery,
            decide(marked = true, viaNewIntent = false, token = "t", handledToken = "other"),
        )
    }

    @Test
    fun `an unmarked onNewIntent replaces the record even for an identical payload`() {
        // A user who shares the same line twice while the app is open must win
        // Identity gates redelivery, never delivery, so the
        // new-intent arm sits ahead of the handled-token check.
        assertEquals(ShareIntake.Stage, decide(viaNewIntent = true, token = "same", handledToken = "same"))
    }

    @Test
    fun `a cold redelivery of a handled payload is refused`() {
        // The process-death shape: mark lost, no saved state, the platform
        // rebuilt the task's launch intent — only the durable claim separates
        // it from a first delivery.
        assertEquals(ShareIntake.IgnoreRedelivery, decide(token = "same", handledToken = "same"))
    }

    @Test
    fun `a restored activity keeps the hydrated record instead of re-reading the intent`() {
        val decision = decide(hasSavedState = true, token = "fresh", handledToken = "other")
        assertEquals(ShareIntake.KeepHydrated, decision)
        assertNotEquals("a restore must not rewrite the pending record", ShareIntake.Stage, decision)
    }

    @Test
    fun `re-activation from history never stages`() {
        assertEquals(
            ShareIntake.KeepHydrated,
            decide(launchedFromHistory = true, viaNewIntent = false, token = "t", handledToken = null),
        )
        assertEquals(
            ShareIntake.KeepHydrated,
            decide(launchedFromHistory = true, viaNewIntent = true, token = "t", handledToken = null),
        )
        assertEquals(
            "a history re-activation of an already-handled share is refused outright",
            ShareIntake.IgnoreRedelivery,
            decide(launchedFromHistory = true, viaNewIntent = false, token = "t", handledToken = "t"),
        )
    }

    @Test
    fun `a non-send action is none of the gate's business`() {
        assertEquals(ShareIntake.IgnoreRedelivery, decide(action = null))
        assertEquals(ShareIntake.IgnoreRedelivery, decide(action = "android.intent.action.MAIN"))
        assertEquals(
            ShareIntake.IgnoreRedelivery,
            decide(action = "android.intent.action.SEND_MULTIPLE", viaNewIntent = true),
        )
    }

    // -- the delivery token ----------------------------------------------------

    private fun tokenOf(
        action: String = SharedKindParser.ACTION_SEND,
        mimeType: String? = "text/plain",
        text: String? = "hello",
        streamUri: String? = null,
        title: String? = null,
        subject: String? = null,
    ) = ShareDeliveryToken.of(action, mimeType, text, streamUri, title, subject)

    @Test
    fun `a token is stable for one delivery and differs across payloads`() {
        assertEquals(tokenOf(), tokenOf())
        assertNotEquals(tokenOf(), tokenOf(text = "hello there"))
        assertNotEquals(tokenOf(), tokenOf(mimeType = "image/png"))
        assertNotEquals(tokenOf(), tokenOf(streamUri = "content://media/external/images/1"))
        assertNotEquals(tokenOf(), tokenOf(title = "a title"))
        assertNotEquals(tokenOf(), tokenOf(subject = "a subject"))
        assertNotEquals(tokenOf(action = "android.intent.action.MAIN"), tokenOf())
    }

    @Test
    fun `a token tolerates every null combination`() {
        val a = tokenOf(mimeType = null, text = null, streamUri = null, title = null, subject = null)
        val b = ShareDeliveryToken.of(SharedKindParser.ACTION_SEND, null, null, null, null, null)
        assertEquals(a, b)
        assertEquals(16, a.length)
    }

    @Test
    fun `a token is sixteen lowercase hex characters`() {
        val token = tokenOf()
        assertEquals(16, token.length)
        assertTrue(token.all { it in "0123456789abcdef" })
    }
}
