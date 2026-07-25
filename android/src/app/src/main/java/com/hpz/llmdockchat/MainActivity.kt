package com.hpz.llmdockchat

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
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
import com.hpz.llmdockchat.core.AppContainer
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.prefs.valueOrNull
import com.hpz.llmdockchat.core.ui.theme.LLMDockChatTheme
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.navigation.AppNavHost
import com.hpz.llmdockchat.navigation.startDestination

class MainActivity : ComponentActivity() {

    @OptIn(ExperimentalComposeUiApi::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as LlmDockApplication).container
        setContent {
            LLMDockChatTheme {
                Scaffold(
                    modifier = Modifier
                        .fillMaxSize()
                        // Surfaces Compose test tags as resource ids, so a
                        // `uiautomator` dump can name what it is tapping.
                        .semantics { testTagsAsResourceId = true },
                    containerColor = LlmTheme.colors.app,
                ) { innerPadding ->
                    AppRoot(container, Modifier.padding(innerPadding))
                }
            }
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
        AppNavHost(
            container = container,
            startDestination = destination,
            modifier = modifier.testTag("app_root"),
        )
    }
}
