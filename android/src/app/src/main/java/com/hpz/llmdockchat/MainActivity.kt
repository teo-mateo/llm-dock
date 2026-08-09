package com.hpz.llmdockchat

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.OpenableColumns
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
import com.hpz.llmdockchat.feature.share.SharedInlineFormatter
import com.hpz.llmdockchat.feature.share.SharedKind
import com.hpz.llmdockchat.feature.share.SharedKindParser
import com.hpz.llmdockchat.feature.share.StagedShare
import com.hpz.llmdockchat.feature.thread.readImage
import com.hpz.llmdockchat.feature.thread.toDataUrl
import com.hpz.llmdockchat.navigation.AppNavHost
import com.hpz.llmdockchat.navigation.startDestination

class MainActivity : ComponentActivity() {

    @OptIn(ExperimentalComposeUiApi::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as LlmDockApplication).container
        stageShareIfAny(intent)
        setContent {
            LLMDockChatTheme {
                // Deliberately edge-to-edge and inset-free: window insets are
                // owned by each screen's own Scaffold, which is the only layer
                // that can put a bar's *background* behind the system bar while
                // padding that bar's *content* clear of it. Consuming them here
                // as well is what produced the grey bands under every screen
                // (fix pass A2), so this layer contributes nothing but a colour.
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
     * F14 — a second share while the app is already open lands here, not in a
     * stacked second activity (`singleTask`). The intent is re-staged and the
     * NavHost's pending-share observer navigates to the picker.
     */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        stageShareIfAny(intent)
    }

    /**
     * F14 — turns a `ACTION_SEND` intent into a staged share, reading the
     * stream *now*: the read grant on a shared `content://` Uri lasts only as
     * long as this activity is alive, so the content must be copied into app
     * storage at intent time (F14-R5). Images go through the same read-and-
     * downscale pipeline as a gallery pick (F04-R9); text files are read and
     * inlined as fenced blocks, web parity (`ChatInput.jsx`).
     */
    private fun stageShareIfAny(intent: Intent) {
        if (intent.action != Intent.ACTION_SEND) return
        val container = (application as LlmDockApplication).container
        val store = container.sharedDraftStore
        val stream = parcelableStream(intent)
        val kind = SharedKindParser.classify(
            action = intent.action.orEmpty(),
            mimeType = intent.type,
            text = intent.getStringExtra(Intent.EXTRA_TEXT),
            title = intent.getStringExtra(Intent.EXTRA_TITLE),
            subject = intent.getStringExtra(Intent.EXTRA_SUBJECT),
            hasStream = stream != null,
            streamName = stream?.let { displayName(it) },
        )
        val share = when (kind) {
            is SharedKind.Text -> StagedShare(text = kind.text)
            is SharedKind.Image -> {
                val uri = stream ?: return
                val bitmap = runCatching { readImage(contentResolver, uri) }.getOrNull()
                if (bitmap == null) {
                    StagedShare(error = "That image could not be read.")
                } else {
                    StagedShare(attachments = listOf(bitmap.toDataUrl()))
                }
            }
            is SharedKind.TextFile -> {
                val uri = stream ?: return
                val content = readSharedTextFile(uri)
                if (content == null) {
                    StagedShare(error = "That file could not be read.")
                } else {
                    StagedShare(text = SharedInlineFormatter.inlineFile(kind.name, content))
                }
            }
            is SharedKind.Unsupported -> StagedShare(error = kind.reason)
        }
        store.stage(share)
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

    private fun displayName(uri: Uri): String? = runCatching {
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0) else null
        }
    }.getOrNull()

    /** Bounded read — a huge file is truncated at the inline cap, not loaded whole. */
    private fun readSharedTextFile(uri: Uri): String? = runCatching {
        contentResolver.openInputStream(uri)?.use { stream ->
            val max = SharedKindParser.MAX_INLINE_BYTES
            val buffer = ByteArray(max + 1)
            var total = 0
            while (total <= max) {
                val n = stream.read(buffer, total, max + 1 - total)
                if (n < 0) break
                total += n
            }
            String(buffer, 0, minOf(total, max), Charsets.UTF_8)
        }
    }.getOrNull()
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
