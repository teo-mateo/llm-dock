package com.hpz.llmdockchat.feature.foundation

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
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.net.BaseUrl
import com.hpz.llmdockchat.core.prefs.Stored
import com.hpz.llmdockchat.core.ui.theme.ChipColors
import com.hpz.llmdockchat.core.ui.theme.LLMDockChatTheme
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

/**
 * Placeholder until F01 brings the Connect screen. It doubles as the palette
 * proof sheet for F00-R7: every token that later features depend on is on
 * screen, so a dark/light screenshot pair shows whether both are styled.
 */
@Composable
fun FoundationScreen(serverUrl: Stored<BaseUrl>, modifier: Modifier = Modifier) {
    val colors = LlmTheme.colors
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(colors.app)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("LLM-Dock", style = MaterialTheme.typography.titleLarge, color = colors.fg)
        Text(
            "Foundation build. The Connect screen arrives with F01.",
            style = MaterialTheme.typography.bodyMedium,
            color = colors.muted,
        )

        Card("Server") {
            when (serverUrl) {
                Stored.Loading -> Text(
                    "Reading settings…",
                    style = MaterialTheme.typography.bodyLarge,
                    color = colors.subtle,
                )
                is Stored.Ready -> Text(
                    serverUrl.value?.value ?: "Not configured",
                    style = MaterialTheme.typography.bodyLarge,
                    color = if (serverUrl.value != null) colors.fg else colors.subtle,
                )
            }
        }

        Card("Engine chips") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Chip("llama.cpp", colors.engineLlamaCpp)
                Chip("vLLM", colors.engineVllm)
                Chip("ds4", colors.engineDs4)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Chip("OpenRouter", colors.engineOpenRouter)
                Chip("unknown", colors.engineUnknown)
            }
        }

        Card("Log levels") {
            LogLine("ERROR  CUDA out of memory", colors.logError)
            LogLine("WARN   falling back to CPU", colors.logWarn)
            LogLine("INFO   server listening on 8080", colors.logInfo)
            LogLine("       untagged output line", colors.logPlain)
        }

        Card("Status") {
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Dot("running", colors.green)
                Dot("starting", colors.amber)
                Dot("stopped", colors.subtle)
                Dot("error", colors.red)
            }
        }
    }
}

@Composable
private fun Card(title: String, content: @Composable () -> Unit) {
    val colors = LlmTheme.colors
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(colors.surface, RoundedCornerShape(14.dp))
            .border(1.dp, colors.line, RoundedCornerShape(14.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(
            title.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = colors.subtle,
        )
        content()
    }
}

@Composable
private fun Chip(label: String, chip: ChipColors) {
    Text(
        label,
        style = MaterialTheme.typography.labelMedium,
        color = chip.foreground,
        modifier = Modifier
            .background(chip.background, RoundedCornerShape(6.dp))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    )
}

@Composable
private fun LogLine(text: String, color: Color) {
    Text(
        text,
        style = MaterialTheme.typography.bodyMedium,
        fontFamily = FontFamily.Monospace,
        color = color,
    )
}

@Composable
private fun Dot(label: String, color: Color) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(modifier = Modifier.size(9.dp).background(color, CircleShape))
        Text(label, style = MaterialTheme.typography.labelMedium, color = LlmTheme.colors.muted)
    }
}

@Preview
@Composable
private fun FoundationScreenDarkPreview() {
    LLMDockChatTheme(darkTheme = true) { FoundationScreen(serverUrl = Stored.Ready(null)) }
}

@Preview
@Composable
private fun FoundationScreenLightPreview() {
    LLMDockChatTheme(darkTheme = false) {
        FoundationScreen(serverUrl = Stored.Ready(BaseUrl.restore("http://10.0.2.2:3399")))
    }
}
