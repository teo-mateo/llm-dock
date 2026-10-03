package com.hpz.llmdockchat

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import com.hpz.llmdockchat.core.prefs.LocalChatAppearance
import com.hpz.llmdockchat.core.AppContainer
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.prefs.valueOrNull
import com.hpz.llmdockchat.core.ui.theme.LLMDockChatTheme
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.share.ShareDeliveryToken
import com.hpz.llmdockchat.feature.share.ShareIntake
import com.hpz.llmdockchat.feature.share.ShareIntakeGate
import com.hpz.llmdockchat.feature.share.ShareRequest
import com.hpz.llmdockchat.navigation.AppNavHost
import com.hpz.llmdockchat.navigation.startDestination

class MainActivity : ComponentActivity() {

    @OptIn(ExperimentalComposeUiApi::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as LlmDockApplication).container
        intakeShare(intent, viaNewIntent = false, hasSavedState = savedInstanceState != null)
        setContent {
            LLMDockChatTheme {
                // Deliberately edge-to-edge and inset-free: window insets are
                // owned by each screen's own Scaffold, which is the only layer
                // that can put a bar's *background* behind the system bar while
                // padding that bar's *content* clear of it. Consuming them here
                // as well is what produced the grey bands under every screen
                //, so this layer contributes nothing but a colour.
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(LlmTheme.colors.app)
                        // Surfaces Compose test tags as resource ids, so a
                        // `uiautomator` dump can name what it is tapping.
                        .semantics { testTagsAsResourceId = true },
                ) {
                    AppRoot(container)
                }
            }
        }
    }

    /**
     * A second share while the app is already open lands here, not in a
     * stacked second activity (`singleTask`). The intake gate stages it and
     * the NavHost's pending-share observer navigates to the picker.
     */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        intakeShare(intent, viaNewIntent = true, hasSavedState = false)
    }

    /**
     * Turns an arriving `ACTION_SEND` intent into a staged share.
     *
     * Only the delivery's *identity* is claimed here, on the main thread: the
     * content behind `EXTRA_STREAM` is read on the application's I/O scope,
     * because a provider stream can stall for as long as it likes and this runs
     * inside `onCreate`. That scope outlives this activity, and the read grant on
     * a shared `content://` Uri does not: a grant Android has already revoked
     * surfaces as the typed failure the picker shows, and a placeholder left
     * behind by a killed process is not rehydrated, so the user re-shares. Text
     * shares and refusals need no read at all and are staged here, synchronously.
     *
     * Issue 261 — the gate decides whether this intent is a delivery to serve
     * or a redelivery to refuse, because Android hands the same launch intent
     * back on every recreation. The mark is stamped before the content read:
     * a stream read can throw or fail, and a served delivery must stay served
     * whatever the read did. `mark` + `setIntent` run on every decision,
     * including refusals: the activity's own launch intent must stop looking
     * unhandled to the next recreation, independent of whether the durable
     * ledger is still on disk — the cache dir is reclaimable.
     */
    private fun intakeShare(intent: Intent, viaNewIntent: Boolean, hasSavedState: Boolean) {
        val container = (application as LlmDockApplication).container
        val store = container.sharedDraftStore
        val marked = intent.getStringExtra(ShareDeliveryToken.EXTRA_MARK)
        val stream = parcelableStream(intent)
        val request = ShareRequest(
            action = intent.action.orEmpty(),
            mimeType = intent.type,
            text = intent.getStringExtra(Intent.EXTRA_TEXT),
            title = intent.getStringExtra(Intent.EXTRA_TITLE),
            subject = intent.getStringExtra(Intent.EXTRA_SUBJECT),
            streamUri = stream?.toString(),
            streamHint = stream?.lastPathSegment,
        )
        val token = marked ?: ShareDeliveryToken.of(
            action = request.action,
            mimeType = request.mimeType,
            text = request.text,
            streamUri = request.streamUri,
            title = request.title,
            subject = request.subject,
        )
        val decision = ShareIntakeGate.decide(
            action = intent.action,
            viaNewIntent = viaNewIntent,
            marked = marked != null,
            launchedFromHistory =
                intent.flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY != 0,
            hasSavedState = hasSavedState,
            token = token,
            handledToken = store.handledToken,
        )
        ShareDeliveryToken.mark(intent, token)
        setIntent(intent)
        when (decision) {
            ShareIntake.IgnoreRedelivery -> return
            ShareIntake.KeepHydrated -> store.rememberHandled(token)
            ShareIntake.Stage -> container.shareIntake.submit(token, request)
        }
    }

    private fun parcelableStream(intent: Intent): Uri? {
        val extra = Intent.EXTRA_STREAM
        return if (Build.VERSION.SDK_INT >= 33) {
            intent.getParcelableExtra(extra, Uri::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableExtra(extra)
        }
    }
}

/**
 * Decides where the app opens, once the three stored values it depends on have
 * come off disk. Nothing renders before then: showing Connect for two frames
 * and then replacing it would flash a login screen at a signed-in user.
 */
@Composable
private fun AppRoot(container: AppContainer, modifier: Modifier = Modifier) {
    val server by container.serverUrlStore.baseUrl.collectAsState()
    val token by container.tokenStore.token.collectAsState()
    val credential by container.credentialStore.hasCredential.collectAsState()

    val hydrated = server !is Stored.Loading &&
        token !is Stored.Loading &&
        credential !is Stored.Loading

    var start by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(hydrated) {
        if (hydrated && start == null) {
            start = startDestination(
                server = server.valueOrNull,
                token = token.valueOrNull,
                hasCredential = credential.valueOrNull == true,
            )
        }
    }

    start?.let { destination ->
        // Provided at the root, not per screen: the chat text size is one
        // app-wide setting, and every screen that reads it must see the same
        // instance or the value would reset on navigation.
        CompositionLocalProvider(LocalChatAppearance provides container.chatAppearance) {
            AppNavHost(
                container = container,
                startDestination = destination,
                modifier = modifier.testTag("app_root"),
            )
        }
    }
}
