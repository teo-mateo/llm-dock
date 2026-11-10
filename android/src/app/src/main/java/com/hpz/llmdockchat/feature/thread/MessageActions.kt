package com.hpz.llmdockchat.feature.thread

import android.content.Intent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

/** Copies the message's raw Markdown source — not the rendered text. */
@Composable
fun MessageActionsRow(content: String, modifier: Modifier = Modifier) {
    val colors = LlmTheme.colors
    val clipboard = LocalClipboardManager.current
    val context = LocalContext.current
    var copied by remember { mutableStateOf(false) }
    LaunchedEffect(copied) {
        if (copied) {
            kotlinx.coroutines.delay(1200)
            copied = false
        }
    }
    Row(modifier.testTag("message_actions"), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(
            if (copied) "Copied" else "Copy",
            color = if (copied) colors.green else colors.subtle,
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier
                .clickable {
                    clipboard.setText(AnnotatedString(content))
                    copied = true
                }
                .testTag("message_copy"),
        )
        Text(
            "Share",
            color = colors.subtle,
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier
                .clickable {
                    val send = Intent(Intent.ACTION_SEND).apply {
                        type = "text/plain"
                        putExtra(Intent.EXTRA_TEXT, content)
                    }
                    context.startActivity(Intent.createChooser(send, null))
                }
                .testTag("message_share"),
        )
    }
}
