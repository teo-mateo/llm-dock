package com.hpz.llmdockchat.feature.designlab

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.feature.designlab.icons.DesignLabIcons
import com.hpz.llmdockchat.feature.designlab.theme.DesignLabTheme

/**
 * Mockup — models list with a GPU header. Compared against `ModelsScreen`.
 */
@Composable
fun MockModelsListScreen() {
    val colors = DesignLabTheme.colors
    Box(Modifier.fillMaxSize().background(colors.appGradient)) {
        Column(Modifier.fillMaxSize()) {
            Text(
                "Models",
                style = MaterialTheme.typography.displaySmall,
                color = colors.fg,
                modifier = Modifier.padding(start = 20.dp, top = 20.dp, bottom = 4.dp),
            )
            GpuHeaderCard(Modifier.padding(horizontal = 16.dp))

            LazyColumn(
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(MOCK_SERVICES) { service -> ServiceRow(service) }
            }
        }
    }
}

@Composable
private fun GpuHeaderCard(modifier: Modifier = Modifier) {
    val colors = DesignLabTheme.colors
    val fraction = (MOCK_GPU_USED_GB / MOCK_GPU_TOTAL_GB).toFloat()
    DlCard(modifier.padding(top = 12.dp)) {
        Column {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(DesignLabIcons.Chip, contentDescription = null, tint = colors.accent, modifier = Modifier.size(18.dp))
                    Text("RTX PRO 6000 Blackwell", style = MaterialTheme.typography.titleMedium, color = colors.fg)
                }
                Text("${(MOCK_GPU_UTIL * 100).toInt()}%", style = MaterialTheme.typography.titleMedium, color = colors.accent)
            }
            Box(
                Modifier
                    .fillMaxWidth()
                    .padding(top = 12.dp)
                    .height(8.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(colors.surfaceHigh),
            ) {
                Box(
                    Modifier
                        .fillMaxWidth(fraction)
                        .height(8.dp)
                        .clip(RoundedCornerShape(4.dp))
                        .background(colors.accent),
                )
            }
            Text(
                "%.1f GB / %.0f GB VRAM".format(MOCK_GPU_USED_GB, MOCK_GPU_TOTAL_GB),
                style = MaterialTheme.typography.labelMedium,
                color = colors.subtle,
                modifier = Modifier.padding(top = 6.dp),
            )
        }
    }
}

@Composable
private fun ServiceRow(service: MockService) {
    val colors = DesignLabTheme.colors
    val (chipBg, chipFg) = engineChipColors(service.engine)
    DlCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            DlIconBadge(
                icon = DesignLabIcons.Chip,
                tint = if (service.running) colors.green else colors.subtle,
                background = if (service.running) colors.accentSoft else colors.surfaceHigh,
            )
            Column(Modifier.weight(1f)) {
                Text(service.name, style = MaterialTheme.typography.titleMedium, color = colors.fg, maxLines = 1)
                Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    DlChip(service.engine, chipBg, chipFg)
                    DlChip(":${service.port}", colors.surfaceHigh, colors.subtle)
                    if (service.running) DlChip(service.vram, colors.surfaceHigh, colors.subtle)
                }
            }
            Box(
                Modifier
                    .size(34.dp)
                    .clip(CircleShape)
                    .background(if (service.running) colors.surfaceHigh else colors.accentSoft),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    if (service.running) DesignLabIcons.Power else DesignLabIcons.Play,
                    contentDescription = if (service.running) "Stop" else "Start",
                    tint = if (service.running) colors.red else colors.accent,
                    modifier = Modifier.size(16.dp),
                )
            }
        }
    }
}

@Preview(name = "Models list — dark", showBackground = true, widthDp = 411, heightDp = 914)
@Composable
private fun MockModelsListDarkPreview() {
    DesignLabTheme(darkTheme = true) { MockModelsListScreen() }
}

@Preview(name = "Models list — light", showBackground = true, widthDp = 411, heightDp = 914)
@Composable
private fun MockModelsListLightPreview() {
    DesignLabTheme(darkTheme = false) { MockModelsListScreen() }
}
