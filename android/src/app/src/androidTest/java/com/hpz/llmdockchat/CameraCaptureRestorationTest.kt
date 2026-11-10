package com.hpz.llmdockchat

import androidx.compose.material3.Text
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.junit4.StateRestorationTester
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import com.hpz.llmdockchat.feature.thread.PendingCapture
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

/**
 * The camera result arrives in a process that may not be the one that launched
 * the camera. What has to survive is the destination Uri, and the only way to
 * prove it is the saved-state bundle the activity itself writes — a plain map
 * in a unit test would prove the saver and nothing about recreation.
 */
class CameraCaptureRestorationTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun aPendingCaptureSurvivesSavedStateRestoration() {
        val restoration = StateRestorationTester(compose)
        lateinit var state: MutableState<PendingCapture>

        restoration.setContent {
            val pending = rememberSaveable(stateSaver = PendingCapture.Saver) {
                mutableStateOf(PendingCapture())
            }
            state = pending
            Text(
                pending.value.destination ?: "none",
                modifier = Modifier.testTag("capture_destination"),
            )
        }

        compose.runOnIdle { state.value = PendingCapture(destination = "content://capture/1") }
        compose.onNodeWithTag("capture_destination").assertTextEquals("content://capture/1")

        restoration.emulateSavedInstanceStateRestore()

        compose.onNodeWithTag("capture_destination").assertTextEquals("content://capture/1")
        compose.runOnIdle {
            assertEquals("content://capture/1", state.value.destination)
        }
    }
}
