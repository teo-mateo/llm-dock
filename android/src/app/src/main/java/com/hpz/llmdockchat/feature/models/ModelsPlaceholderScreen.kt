package com.hpz.llmdockchat.feature.models

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
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
 * Placeholder for the Models tab (F10). F02 only needs it to exist as a
 * bottom-bar destination so the two-tab scaffold has somewhere to switch to
 * (Architecture D12) — start/stop, logs and everything else in `docs/F10-…`
 * is out of scope here.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModelsPlaceholderScreen(modifier: Modifier = Modifier) {
    val colors = LlmTheme.colors
    Scaffold(
        modifier = modifier.testTag("models_placeholder_screen"),
        containerColor = colors.app,
        topBar = {
            TopAppBar(
                title = { Text("Models", color = colors.fg) },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.app),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text("Coming in F10", color = colors.fg, style = MaterialTheme.typography.titleMedium)
            Text(
                "Model start, stop and logs land here.",
                color = colors.muted,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}
