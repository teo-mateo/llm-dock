package com.hpz.llmdockchat.feature.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LLMDockChatTheme
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

/**
 * Placeholder for the conversation list (F02). It shows what F01 can prove:
 * which server the app is talking to, that the stored session actually works,
 * and the way back out (F01-R7).
 */
@Composable
fun HomeScreen(viewModel: HomeViewModel, onSignedOut: () -> Unit, modifier: Modifier = Modifier) {
    val state by viewModel.state.collectAsState()
    HomeContent(
        state = state,
        onRetry = viewModel::verify,
        onSignOut = {
            viewModel.signOut()
            onSignedOut()
        },
        modifier = modifier,
    )
}

@Composable
private fun HomeContent(
    state: HomeUiState,
    onRetry: () -> Unit,
    onSignOut: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LlmTheme.colors
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(colors.app)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("llm-dock", style = MaterialTheme.typography.titleLarge, color = colors.fg)
        Text(
            "Signed in. The conversation list arrives with F02.",
            style = MaterialTheme.typography.bodyMedium,
            color = colors.muted,
        )

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(colors.surface, RoundedCornerShape(14.dp))
                .border(1.dp, colors.line, RoundedCornerShape(14.dp))
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                "SESSION",
                style = MaterialTheme.typography.labelSmall,
                color = colors.subtle,
            )
            Text(
                state.server.ifBlank { "No server configured" },
                style = MaterialTheme.typography.bodyLarge,
                color = colors.fg,
            )
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                val (dot, label) = when {
                    state.checking -> colors.amber to "Checking the session…"
                    state.sessionValid -> colors.green to "Session verified"
                    else -> colors.red to (state.failure ?: "Session not usable")
                }
                Box(Modifier.size(9.dp).background(dot, CircleShape))
                Text(
                    label,
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.muted,
                    modifier = Modifier.testTag("home_session_status"),
                )
            }
            if (!state.checking && !state.sessionValid) {
                TextButton(onClick = onRetry, modifier = Modifier.testTag("home_retry")) {
                    Text("Retry", color = colors.accent)
                }
            }
        }

        OutlinedButton(
            onClick = onSignOut,
            modifier = Modifier
                .fillMaxWidth()
                .testTag("home_sign_out"),
        ) {
            Text("Sign out", color = colors.red)
        }
    }
}

@Preview
@Composable
private fun HomeDarkPreview() {
    LLMDockChatTheme(darkTheme = true) {
        HomeContent(
            state = HomeUiState(
                server = "http://10.0.2.2:3399",
                checking = false,
                sessionValid = true,
            ),
            onRetry = {}, onSignOut = {},
        )
    }
}

@Preview
@Composable
private fun HomeLightPreview() {
    LLMDockChatTheme(darkTheme = false) {
        HomeContent(
            state = HomeUiState(
                server = "https://dock.example",
                checking = false,
                failure = "Could not reach the server.",
            ),
            onRetry = {}, onSignOut = {},
        )
    }
}
