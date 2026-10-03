package com.hpz.llmdockchat

import android.app.Activity
import android.content.Context
import android.content.Intent
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.hpz.llmdockchat.feature.share.SharedDraftStore
import com.hpz.llmdockchat.testing.ShareIntents
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Recreation must never replay a consumed share. Everything routes
 * through the real activity + container + cache dir — the unit suite cannot
 * launch activities, and the stubs cannot build `Intent`s, so the redelivery
 * round trip (mark written, `setIntent`, parcel copy back through
 * `savedInstanceState`) is only provable on a device.
 */
@RunWith(AndroidJUnit4::class)
class ShareRecreationInstrumentedTest {

    private val targetContext: Context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun store(activity: Activity): SharedDraftStore =
        (activity.application as LlmDockApplication).container.sharedDraftStore

    private fun pendingFile() = File(File(targetContext.cacheDir, "shared-drafts"), "pending.json")

    private fun pendingState(activity: Activity): String? =
        store(activity).pending.value?.let { it.text + it.attachments.joinToString() + (it.error ?: "") }

    @Test
    fun aConsumedShareDoesNotComeBackOnRecreate() {
        val scenario = ActivityScenario.launch<MainActivity>(
            ShareIntents.textShare(targetContext, "ANDROID_REVIEW_FIRST_SHARE"),
        )
        scenario.onActivity {
            assertEquals("ANDROID_REVIEW_FIRST_SHARE", store(it).pending.value?.text)
            store(it).clearPending()
            assertNull(store(it).pending.value)
        }
        scenario.recreate()
        scenario.onActivity {
            assertNull("a consumed share must not be re-staged by recreation", store(it).pending.value)
        }
        scenario.close()
    }

    @Test
    fun recreateWhileThePickerIsOpenPreservesExactlyOneRecord() {
        val scenario = ActivityScenario.launch<MainActivity>(
            ShareIntents.textShare(targetContext, "ANDROID_REVIEW_PICKER_OPEN"),
        )
        scenario.onActivity { assertNotNull(store(it).pending.value) }
        val modifiedBefore = pendingFile().lastModified()
        val pendingBefore: String? = scenario.activityStore { pendingState(it) }
        scenario.recreate()
        scenario.onActivity {
            assertEquals("the one pending record must survive untouched", pendingBefore, pendingState(it))
            assertEquals("recreation must not rewrite pending.json", modifiedBefore, pendingFile().lastModified())
        }
        scenario.onActivity { store(it).clearPending() }
        scenario.close()
    }

    @Test
    fun aSecondShareDeliveredToTheRunningActivityReplacesTheRecord() {
        val first = ShareIntents.textShare(targetContext, "ANDROID_REVIEW_REPLACE_A")
        val second = ShareIntents.textShare(targetContext, "ANDROID_REVIEW_REPLACE_B")
        val scenario = ActivityScenario.launch<MainActivity>(first)
        scenario.onActivity {
            assertEquals("ANDROID_REVIEW_REPLACE_A", store(it).pending.value?.text)
        }
        // singleTask: a second launch into the same task lands in onNewIntent
        // of the existing instance, not a stacked activity.
        val secondScenario = ActivityScenario.launch<MainActivity>(second)
        secondScenario.onActivity {
            assertEquals("ANDROID_REVIEW_REPLACE_B", store(it).pending.value?.text)
            assertEquals(
                "the new delivery is the handled claim now",
                ShareIntents.expectedTextToken("ANDROID_REVIEW_REPLACE_B"),
                store(it).handledToken,
            )
            store(it).clearPending()
        }
        scenario.closeQuietly()
        secondScenario.close()
    }

    @Test
    fun theRecreateAfterAnImageShareKeepsTheStagedDataUrl() {
        val (uri, intent) = ShareIntents.imageShare(targetContext, "recreate-check")
        assertNotNull(uri)
        val scenario = ActivityScenario.launch<MainActivity>(intent)
        scenario.onActivity {
            val staged = store(it).pending.value
            assertNotNull("the image share must stage", staged)
            assertTrue(
                "the attachment must already be an in-process data URL",
                staged?.attachments?.single()?.startsWith("data:image/jpeg;base64,") == true,
            )
        }
        val modifiedBefore = pendingFile().lastModified()
        val pendingBefore: String? = scenario.activityStore { pendingState(it) }
        scenario.recreate()
        scenario.onActivity {
            assertEquals(pendingBefore, pendingState(it))
            assertEquals("recreation must not rewrite pending.json", modifiedBefore, pendingFile().lastModified())
            store(it).clearPending()
        }
        scenario.close()
    }

    @Test
    fun aHandledShareRedeliveredToAColdOnCreateDoesNotReplay() {
        // Not force-stopped: `am force-stop` kills the app-under-test, which also
        // hosts this instrumentation, so it crashes the runner. The process-death
        // signal that matters is a fresh onCreate handed the task's rebuilt, unmarked
        // launch intent for a payload already claimed; only the durable handled token
        // separates it from a first delivery (gate arm 4). Closing the scenario
        // destroys the activity while the Application and its hydrated store live on,
        // so a relaunch re-enters onCreate over that claim. That the claim is read from
        // disk after a real kill is covered by the SharedDraftStore JVM test that a
        // fresh store over the same dir reports the handled token.
        val scenario = ActivityScenario.launch<MainActivity>(
            ShareIntents.textShare(targetContext, "ANDROID_REVIEW_PROCESS_DEATH"),
        )
        scenario.onActivity {
            assertEquals("ANDROID_REVIEW_PROCESS_DEATH", store(it).pending.value?.text)
            store(it).clearPending()
            assertNotNull("the durable claim must outlive the record", store(it).handledToken)
        }
        scenario.close()
        val redelivered = ShareIntents.textShare(targetContext, "ANDROID_REVIEW_PROCESS_DEATH")
            .apply { addFlags(Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY) }
        val relaunched = ActivityScenario.launch<MainActivity>(redelivered)
        relaunched.onActivity {
            assertNull(
                "a redelivery of a handled payload must not re-stage it",
                store(it).pending.value,
            )
            assertNotNull("the claim survives the activity restart", store(it).handledToken)
        }
        relaunched.closeQuietly()
    }

    private fun <T> ActivityScenario<MainActivity>.activityStore(block: (Activity) -> T): T {
        var result: T? = null
        onActivity { result = block(it) }
        return result as T
    }

    private fun ActivityScenario<MainActivity>.closeQuietly() {
        runCatching { close() }
    }
}
