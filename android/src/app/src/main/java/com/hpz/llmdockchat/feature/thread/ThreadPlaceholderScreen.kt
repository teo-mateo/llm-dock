package com.hpz.llmdockchat.feature.thread

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

/**
 * Placeholder for the thread itself (F04). Not one of the two placeholders
 * the F02 brief names (F10 Models, F03 new-chat) — it exists because
 * opening a row has nowhere real to go yet. See F02-conversation-list.md's
 * *Deviations* for why this was added: F02-R3's "tapping such a row opens
 * the thread already streaming, mid-answer" cannot be verified until F04
 * exists, so it is carried forward the same way F00's screen-level criteria
 * were carried forward to F02.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ThreadPlaceholderScreen(title: String, onBack: () -> Unit, modifier: Modifier = Modifier) {
    val colors = LlmTheme.colors
    Scaffold(
        modifier = modifier.testTag("thread_placeholder_screen"),
        containerColor = colors.app,
        topBar = {
            TopAppBar(
                title = { Text(title, color = colors.fg, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    IconButton(onClick = onBack, modifier = Modifier.testTag("thread_back")) {
                        Text("←", color = colors.fg)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.app),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text("Coming in F04", color = colors.fg, style = MaterialTheme.typography.titleMedium)
            Text(
                "Streaming, tool calls and reattach to an active run land here.",
                color = colors.muted,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}
