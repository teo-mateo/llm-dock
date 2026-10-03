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
 * Legacy placeholder for the thread itself, no longer reachable. It existed
  * because opening a row had nowhere real to go, and "tap a row, find the
  * thread already streaming mid-answer" could not be verified until a
  * thread screen existed.
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
