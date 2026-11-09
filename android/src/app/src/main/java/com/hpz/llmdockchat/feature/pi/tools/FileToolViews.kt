package com.hpz.llmdockchat.feature.pi.tools

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.feature.pi.transcript.tools.NumberedLine
import com.hpz.llmdockchat.feature.pi.transcript.tools.ToolImage
import com.hpz.llmdockchat.feature.pi.transcript.tools.splitPath
import java.util.Base64

@Composable
internal fun PathHeader(path: String) {
    val colors = LlmTheme.colors
    val split = splitPath(path)
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        if (split.dir.isNotEmpty()) {
            Text(
                split.dir,
                color = colors.muted,
                fontFamily = MonoFontFamily,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false),
            )
        }
        Text(
            split.name,
            color = colors.fg,
            fontFamily = MonoFontFamily,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.bodySmall,
            maxLines = 1,
        )
    }
}

@Composable
internal fun NumberedText(itemId: String, slot: String, lines: List<NumberedLine>, cap: Int) {
    CappedToolRows(itemId, slot, lines, cap, "pi_tool_output_toggle") { NumberedLineRow(it) }
}

@Composable
private fun NumberedLineRow(line: NumberedLine) {
    val colors = LlmTheme.colors
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            line.number.toString(),
            color = colors.muted,
            fontFamily = MonoFontFamily,
            style = MaterialTheme.typography.bodySmall,
            textAlign = TextAlign.End,
            modifier = Modifier.width(44.dp),
        )
        Text(
            line.text,
            color = colors.fg,
            fontFamily = MonoFontFamily,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
internal fun ToolImageView(image: ToolImage) {
    val colors = LlmTheme.colors
    val bitmap = remember(image.base64) {
        runCatching {
            val bytes = Base64.getDecoder().decode(image.base64)
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.asImageBitmap()
        }.getOrNull()
    }
    if (bitmap != null) {
        Image(
            bitmap = bitmap,
            contentDescription = null,
            contentScale = ContentScale.FillWidth,
            modifier = Modifier.fillMaxWidth().heightIn(max = 240.dp),
        )
    } else {
        Text(
            "Read image file [${image.mimeType}]",
            color = colors.muted,
            fontFamily = MonoFontFamily,
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
