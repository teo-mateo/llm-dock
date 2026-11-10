package com.hpz.llmdockchat.core.ui.render

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

/**
 * Collapsed by default, and never mixed into the answer body. Absent
 * entirely when the model emitted no reasoning, so a non-thinking model shows
 * no empty block.
 */
@Composable
fun ReasoningBlock(reasoning: String) {
    val colors = LlmTheme.colors
    var expanded by remember { mutableStateOf(false) }
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.sunken)
            .clickable { expanded = !expanded }
            .padding(horizontal = 10.dp, vertical = 6.dp)
            .testTag("reasoning_block"),
        verticalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(7.dp)) {
            Text(if (expanded) "▾" else "▸", color = colors.subtle, style = MaterialTheme.typography.labelSmall)
            Text(
                "Reasoning",
                color = colors.muted,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.weight(1f),
            )
            Text("${reasoning.length} chars", color = colors.subtle, style = MaterialTheme.typography.labelSmall)
        }
        if (expanded) {
            Text(
                reasoning,
                color = colors.muted,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("reasoning_text"),
            )
        }
    }
}
