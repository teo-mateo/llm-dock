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
import androidx.compose.runtime.produceState
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
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
import com.hpz.llmdockchat.feature.pi.transcript.tools.imageSampleSize
import com.hpz.llmdockchat.feature.pi.transcript.tools.splitPath
import java.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

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

private sealed interface ToolImageState {
    data object Loading : ToolImageState
    data class Loaded(val bitmap: ImageBitmap) : ToolImageState
    data object Failed : ToolImageState
}

private const val IMAGE_MAX_DIMENSION = 1024
private const val IMAGE_MAX_BYTES = 6 * 1024 * 1024

@Composable
internal fun ToolImageView(image: ToolImage) {
    val colors = LlmTheme.colors
    val state = produceState<ToolImageState>(ToolImageState.Loading, image.base64) {
        value = withContext(Dispatchers.Default) {
            val bitmap = decodeToolImage(image)
            if (bitmap != null) ToolImageState.Loaded(bitmap) else ToolImageState.Failed
        }
    }.value
    when (val current = state) {
        is ToolImageState.Loaded -> Image(
            bitmap = current.bitmap,
            contentDescription = null,
            contentScale = ContentScale.FillWidth,
            modifier = Modifier.fillMaxWidth().heightIn(max = 240.dp),
        )
        ToolImageState.Failed -> Text(
            "Read image file [${image.mimeType}]",
            color = colors.muted,
            fontFamily = MonoFontFamily,
            style = MaterialTheme.typography.bodySmall,
        )
        ToolImageState.Loading -> Unit
    }
}

private fun decodeToolImage(image: ToolImage): ImageBitmap? = runCatching {
    val bytes = Base64.getDecoder().decode(image.base64)
    if (bytes.size > IMAGE_MAX_BYTES) return@runCatching null
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
    val sample = imageSampleSize(bounds.outWidth, bounds.outHeight, IMAGE_MAX_DIMENSION)
    val options = BitmapFactory.Options().apply { inSampleSize = sample }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)?.asImageBitmap()
}.getOrNull()
