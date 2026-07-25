package com.hpz.llmdockchat.feature.toolspicker

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.McpServerInfo

/**
 * Which MCP servers a thread may call (F03-R3, F08), shared by
 * [com.hpz.llmdockchat.feature.newchat.NewChatScreen] (picking a default for
 * a brand-new thread — the batched, not-yet-persisted selection) and
 * [com.hpz.llmdockchat.feature.thread.ThreadScreen] (F08's in-thread sheet,
 * where each [onToggle] is the caller's cue to persist immediately). Grown
 * out of F03's own private composable once F08 needed the same list and row
 * shape for an existing conversation — see F08's report for why sharing it
 * cost nothing: the list of servers, the checkbox row and the Done button are
 * identical in both places, only what a toggle *does* differs, and that
 * belongs to the caller's [onToggle], not to this composable.
 *
 * [hint], when non-null, renders above the list — F08 uses it for the
 * mockup's "Changes apply to the next message you send" (screen 07b); F03
 * passes none, since nothing has been sent yet for that to be true of.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ToolsPickerSheet(
    servers: List<McpServerInfo>,
    selectedIds: Set<String>,
    onToggle: (String) -> Unit,
    onDismiss: () -> Unit,
    hint: String? = null,
) {
    val colors = LlmTheme.colors
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = colors.surface,
        modifier = Modifier.testTag("tools_picker_sheet"),
    ) {
        // C3: the sheet draws behind the navigation bar, so without
        // this its last row is unreachable under the 44 dp button bar.
        LazyColumn(Modifier.fillMaxWidth().navigationBarsPadding()) {
            if (hint != null) {
                item {
                    Text(
                        hint,
                        color = colors.subtle,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                            .testTag("tools_picker_hint"),
                    )
                }
            }
            items(servers, key = { it.id }) { server ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onToggle(server.id) }
                        .padding(horizontal = 16.dp, vertical = 10.dp)
                        .testTag("tool_option_${server.id}"),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Checkbox(
                        checked = server.id in selectedIds,
                        onCheckedChange = { onToggle(server.id) },
                        colors = CheckboxDefaults.colors(checkedColor = colors.accent, uncheckedColor = colors.subtle),
                    )
                    Column(Modifier.weight(1f)) {
                        Text(server.name, color = colors.fg, style = MaterialTheme.typography.bodyLarge)
                        Text(
                            server.description,
                            color = colors.muted,
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
            item {
                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier.fillMaxWidth().padding(16.dp).testTag("tools_picker_done"),
                ) {
                    Text("Done", color = colors.accent)
                }
            }
        }
    }
}
