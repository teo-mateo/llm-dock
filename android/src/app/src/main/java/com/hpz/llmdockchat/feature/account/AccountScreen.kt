package com.hpz.llmdockchat.feature.account

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.ConfirmDialog
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons

/**
 * The signed-in account screen: the server this phone talks to, and the
 * sign-out that was previously nowhere reachable.
 *
 * It is a pushed destination rather than a sheet, so signing out clears it along
 * with every other authenticated screen instead of leaving it floating over a
 * Chats list that can no longer load.
 */
@Composable
fun AccountScreen(
    viewModel: AccountViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()
    var confirming by remember { mutableStateOf(false) }

    AccountContent(
        state = state,
        confirming = confirming,
        onBack = onBack,
        onSignOutRequest = { confirming = true },
        onSignOutConfirm = {
            confirming = false
            viewModel.signOut()
        },
        onSignOutDismiss = { confirming = false },
        modifier = modifier,
    )
}

@Composable
private fun AccountContent(
    state: AccountUiState,
    confirming: Boolean,
    onBack: () -> Unit,
    onSignOutRequest: () -> Unit,
    onSignOutConfirm: () -> Unit,
    onSignOutDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LlmTheme.colors

    Box(Modifier.fillMaxSize().background(colors.appGradient)) {
        Scaffold(
            modifier = modifier.testTag("account_screen"),
            containerColor = Color.Transparent,
            topBar = { AccountHeader(onBack = onBack) },
        ) { padding ->
            Column(
                Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 20.dp),
            ) {
                Text(
                    "Server",
                    color = colors.subtle,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.fillMaxWidth().padding(top = 18.dp, bottom = 4.dp),
                )
                Text(
                    state.server ?: "Not set",
                    color = colors.fg,
                    style = MaterialTheme.typography.titleMedium,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.fillMaxWidth().testTag("account_server"),
                )
                Box(
                    Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp)
                        .height(1.dp)
                        .background(colors.line),
                )

                Spacer(Modifier.height(28.dp))
                SignOutButton(onClick = onSignOutRequest)
                Spacer(Modifier.height(24.dp))
            }
        }

        if (confirming) {
            ConfirmDialog(
                icon = DesignLabIcons.Power,
                title = "Sign out?",
                message = "Clears the token and the saved password. The address stays.",
                confirmLabel = "Sign out",
                tint = colors.red,
                onConfirm = onSignOutConfirm,
                onDismiss = onSignOutDismiss,
                testTag = "account_sign_out_dialog",
            )
        }
    }
}

@Composable
private fun AccountHeader(onBack: () -> Unit) {
    val colors = LlmTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.statusBars)
            .height(64.dp)
            .padding(horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(
            onClick = onBack,
            modifier = Modifier.testTag("account_back"),
        ) {
            Icon(
                DesignLabIcons.ChevronLeft,
                contentDescription = "Back",
                tint = colors.fg,
                modifier = Modifier.size(22.dp),
            )
        }
        Text(
            "Account",
            color = colors.fg,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 4.dp),
        )
    }
}

@Composable
private fun SignOutButton(onClick: () -> Unit) {
    val colors = LlmTheme.colors
    Box(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(colors.red)
            .clickable(onClick = onClick)
            .padding(vertical = 14.dp)
            .testTag("account_sign_out"),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            "Sign out",
            color = colors.onAccent,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
        )
    }
}
