package com.hpz.llmdockchat.feature.newchat

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
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

/**
 * Legacy placeholder for the new-chat sheet, no longer reachable. It was a
  * pushed screen rather than a modal from the start, and carries no bottom
  * bar — the same shape the real sheet later kept.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NewChatPlaceholderScreen(onBack: () -> Unit, modifier: Modifier = Modifier) {
    val colors = LlmTheme.colors
    Scaffold(
        modifier = modifier.testTag("new_chat_placeholder_screen"),
        containerColor = colors.app,
        topBar = {
            TopAppBar(
                title = { Text("New chat", color = colors.fg) },
                navigationIcon = {
                    IconButton(onClick = onBack, modifier = Modifier.testTag("new_chat_back")) {
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
            Text("Coming in F03", color = colors.fg, style = MaterialTheme.typography.titleMedium)
            Text(
                "Model, system prompt, tools and project pick here before a chat starts.",
                color = colors.muted,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}
