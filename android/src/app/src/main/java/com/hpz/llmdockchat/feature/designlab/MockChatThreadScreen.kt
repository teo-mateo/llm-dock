package com.hpz.llmdockchat.feature.designlab

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons
import com.hpz.llmdockchat.feature.designlab.theme.DesignLabTheme

/**
 * Mockup — a chat thread: user + assistant turns, a code block, and a
 * streaming indicator. Compared against `ThreadScreen`/`ThreadMessages`.
 */
@Composable
fun MockChatThreadScreen() {
    val colors = DesignLabTheme.colors
    Column(Modifier.fillMaxSize().background(colors.app)) {
        ThreadTopBar()
        LazyColumn(
            modifier = Modifier.weight(1f),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(MOCK_MESSAGES) { message -> MessageBubble(message) }
        }
        ComposerBar()
    }
}

@Composable
private fun ThreadTopBar() {
    val colors = DesignLabTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .background(colors.surface)
            .border(androidx.compose.foundation.BorderStroke(1.dp, colors.line))
            .padding(horizontal = 8.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = {}) {
            Icon(DesignLabIcons.Back, contentDescription = "Back", tint = colors.fg)
        }
        Column(Modifier.weight(1f)) {
            Text(MOCK_THREAD_TITLE, style = MaterialTheme.typography.titleMedium, color = colors.fg, maxLines = 1)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(6.dp).background(colors.green, CircleShape))
                Text(
                    "  llama.cpp · mimo-v2-5-q4",
                    style = MaterialTheme.typography.labelSmall,
                    color = colors.subtle,
                )
            }
        }
    }
}

@Composable
private fun MessageBubble(message: MockMessage) {
    val colors = DesignLabTheme.colors
    val alignment = if (message.fromUser) Alignment.End else Alignment.Start
    Column(Modifier.fillMaxWidth(), horizontalAlignment = alignment) {
        when (message) {
            is MockMessage.Text -> {
                val bg = if (message.fromUser) colors.accent else colors.surfaceElevated
                val fg = if (message.fromUser) colors.onAccent else colors.fg
                Box(
                    Modifier
                        .widthIn(max = 300.dp)
                        .clip(RoundedCornerShape(18.dp))
                        .background(bg)
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                ) {
                    Text(message.body, color = fg, style = MaterialTheme.typography.bodyMedium)
                }
            }
            is MockMessage.Code -> {
                Column(
                    Modifier
                        .widthIn(max = 320.dp)
                        .clip(RoundedCornerShape(14.dp))
                        .background(colors.sunken)
                        .border(1.dp, colors.lineStrong, RoundedCornerShape(14.dp)),
                ) {
                    Row(
                        Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(message.language, style = MaterialTheme.typography.labelSmall, color = colors.subtle)
                        Icon(DesignLabIcons.Copy, contentDescription = "Copy", tint = colors.subtle, modifier = Modifier.size(15.dp))
                    }
                    Text(
                        message.body,
                        color = colors.muted,
                        fontFamily = FontFamily.Monospace,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                    )
                }
            }
            MockMessage.Streaming -> StreamingBubble()
        }
    }
}

@Composable
private fun StreamingBubble() {
    val colors = DesignLabTheme.colors
    val transition = rememberInfiniteTransition(label = "streaming")
    val phase by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(900, easing = LinearEasing), RepeatMode.Reverse),
        label = "phase",
    )
    Row(
        Modifier
            .clip(RoundedCornerShape(18.dp))
            .background(colors.surfaceElevated)
            .border(1.dp, colors.streaming.copy(alpha = 0.4f), RoundedCornerShape(18.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        repeat(3) { i ->
            val a = ((phase + i * 0.25f) % 1f).let { if (it < 0.5f) it * 2f else (1f - it) * 2f }
            Box(Modifier.size(7.dp).background(colors.streaming.copy(alpha = 0.35f + a * 0.65f), CircleShape))
        }
    }
}

@Composable
private fun ComposerBar() {
    val colors = DesignLabTheme.colors
    Row(
        Modifier
            .fillMaxWidth()
            .background(colors.surface)
            .padding(12.dp),
        verticalAlignment = Alignment.Bottom,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        RoundIconButton(DesignLabIcons.Image, "Attach image")
        RoundIconButton(DesignLabIcons.Camera, "Take photo")
        Box(
            Modifier
                .weight(1f)
                .clip(RoundedCornerShape(22.dp))
                .background(colors.sunken)
                .border(1.dp, colors.line, RoundedCornerShape(22.dp))
                .padding(horizontal = 16.dp, vertical = 12.dp),
        ) {
            Text("Message", color = colors.subtle, style = MaterialTheme.typography.bodyMedium)
        }
        Box(
            Modifier
                .size(44.dp)
                .clip(CircleShape)
                .background(colors.streaming),
            contentAlignment = Alignment.Center,
        ) {
            Icon(DesignLabIcons.Stop, contentDescription = "Stop", tint = Color(0xFF1A1206), modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
private fun RoundIconButton(icon: androidx.compose.ui.graphics.vector.ImageVector, description: String) {
    val colors = DesignLabTheme.colors
    Box(
        Modifier
            .size(44.dp)
            .clip(CircleShape)
            .background(colors.surfaceHigh),
        contentAlignment = Alignment.Center,
    ) {
        Icon(icon, contentDescription = description, tint = colors.muted, modifier = Modifier.size(19.dp))
    }
}

@Preview(name = "Chat thread — dark", showBackground = true, widthDp = 411, heightDp = 914)
@Composable
private fun MockChatThreadDarkPreview() {
    DesignLabTheme(darkTheme = true) { MockChatThreadScreen() }
}

@Preview(name = "Chat thread — light", showBackground = true, widthDp = 411, heightDp = 914)
@Composable
private fun MockChatThreadLightPreview() {
    DesignLabTheme(darkTheme = false) { MockChatThreadScreen() }
}
