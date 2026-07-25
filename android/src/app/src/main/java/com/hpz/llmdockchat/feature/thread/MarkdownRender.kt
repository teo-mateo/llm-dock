package com.hpz.llmdockchat.feature.thread

import android.content.Intent
import android.graphics.Bitmap
import android.webkit.WebView
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.hpz.llmdockchat.core.markdown.MdBlock
import com.hpz.llmdockchat.core.markdown.TableAlign
import com.hpz.llmdockchat.core.markdown.parseMdBlock
import com.hpz.llmdockchat.core.markdown.splitMdBlocks
import com.hpz.llmdockchat.core.ui.theme.LlmColors
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.data.model.ArtifactRecord
import kotlin.math.max
import kotlin.math.min

/**
 * The assistant answer's body (F05-R1/R2/R5/R7): split into blocks, each block
 * memoized on its own raw text so a growing streamed answer only re-parses the
 * one block still being written (Architecture P2 — see
 * `core/markdown/MarkdownParser.kt` for the two-phase design).
 *
 * [selectable] wraps the blocks in one [SelectionContainer] so selection spans
 * every block, not just a single paragraph (F05-R3's second criterion) — but
 * only while the message is in F06's selection mode. A [SelectionContainer]
 * claims long-press for its own selection-start gesture, which is exactly the
 * gesture F06-R1 needs for the action menu; rather than fight that
 * conflict on every message all the time, selection is off by default and
 * turned on per-message from the long-press menu's "Select text" row
 * (`ThreadMessages.kt`'s `LongPressableMessage`), which simultaneously stops
 * offering the long-press gesture for as long as it's on (F06-R4's second
 * criterion). See F06's *Deviations* for why this changes how F05-R3's
 * already-shipped selection is invoked, not whether it works.
 */
@Composable
fun MarkdownBody(raw: String, modifier: Modifier = Modifier, selectable: Boolean = false) {
    val colors = LlmTheme.colors
    val blocks = remember(raw) { splitMdBlocks(raw) }
    val body: @Composable () -> Unit = {
        // 6dp between blocks ran paragraphs together into one grey mass at
        // this body size; 12 is about half a line, which is what separates
        // paragraphs on paper. Headings take more, above only, so a heading
        // binds to the text under it rather than floating between two
        // sections.
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            blocks.forEachIndexed { index, rawBlock ->
                val block = remember(rawBlock, colors) { parseMdBlock(rawBlock, colors) }
                if (block is MdBlock.Heading && index > 0) Spacer(Modifier.height(6.dp))
                MdBlockView(block, colors)
            }
        }
    }
    if (selectable) {
        SelectionContainer(modifier = modifier.testTag("markdown_body"), content = body)
    } else {
        Box(modifier.testTag("markdown_body")) { body() }
    }
}

@Composable
private fun MdBlockView(block: MdBlock, colors: LlmColors) {
    when (block) {
        is MdBlock.Heading -> Text(
            block.text,
            color = colors.fg,
            fontFamily = FontFamily.Serif,
            fontWeight = FontWeight.Bold,
            style = headingStyle(block.level),
        )
        is MdBlock.Paragraph -> Text(
            block.text,
            color = colors.fg,
            fontFamily = FontFamily.Serif,
            style = MaterialTheme.typography.bodyLarge,
        )
        is MdBlock.CodeBlock -> CodeBlockView(block, colors)
        is MdBlock.ListBlock -> ListBlockView(block, colors)
        is MdBlock.Quote -> QuoteView(block, colors)
        is MdBlock.Table -> TableView(block, colors)
        MdBlock.Rule -> HorizontalRuleView(colors)
        is MdBlock.MathBlock -> Text(
            block.source,
            color = colors.muted,
            fontFamily = FontFamily.Monospace,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(8.dp))
                .background(colors.sunken)
                .padding(10.dp),
        )
    }
}

/**
 * Sizes given outright rather than pulled from [MaterialTheme.typography].
 *
 * The theme defines neither `headlineSmall` nor `titleSmall`, so h1 and h4+ were
 * silently falling back to Material's defaults — and Material's `titleSmall` is
 * 14sp, *smaller* than this body text at 16sp. A model that writes `#### ` got a
 * heading that looked like de-emphasised prose. Every level is now at least body
 * size, and each is strictly larger than the one below it.
 */
@Composable
private fun headingStyle(level: Int) = MaterialTheme.typography.bodyLarge.copy(
    fontSize = when (level) {
        1 -> 24.sp
        2 -> 21.sp
        3 -> 18.sp
        else -> 16.sp
    },
    lineHeight = when (level) {
        1 -> 30.sp
        2 -> 27.sp
        3 -> 24.sp
        else -> 22.sp
    },
)

/**
 * F05-R2 — language label, copy button, and its own horizontal scroll so a
 * long line never pushes the message column sideways.
 */
@Composable
private fun CodeBlockView(block: MdBlock.CodeBlock, colors: LlmColors) {
    val clipboard = LocalClipboardManager.current
    var copied by remember { mutableStateOf(false) }
    LaunchedEffect(copied) {
        if (copied) {
            kotlinx.coroutines.delay(1200)
            copied = false
        }
    }
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.sunken)
            .testTag("code_block"),
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .background(colors.surfaceElevated)
                .padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                block.language?.uppercase() ?: "CODE",
                color = colors.subtle,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.weight(1f),
            )
            Text(
                if (copied) "Copied" else "Copy",
                color = if (copied) colors.green else colors.accent,
                style = MaterialTheme.typography.labelMedium,
                modifier = Modifier
                    .clickable {
                        // Exact code only — no fence markers, no reformatting
                        // (F05-R2's second criterion).
                        clipboard.setText(AnnotatedString(block.code))
                        copied = true
                    }
                    .testTag("code_copy"),
            )
        }
        // C4: the padding goes *outside* the scroll container, so the viewport
        // ends at the inset and long lines are clipped there. Inside it, the
        // padding scrolled along with the text and code slid out under the
        // block's own left edge.
        Box(Modifier.fillMaxWidth().padding(10.dp).horizontalScroll(rememberScrollState())) {
            Text(
                block.code,
                color = colors.fg,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun ListBlockView(block: MdBlock.ListBlock, colors: LlmColors) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        block.items.forEach { item ->
            Row(Modifier.padding(start = (item.depth * 16).dp)) {
                val marker = if (item.ordered) "${item.index ?: 1}." else bulletFor(item.depth)
                Text(
                    marker,
                    color = colors.subtle,
                    fontFamily = FontFamily.Serif,
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.width(24.dp),
                )
                Text(
                    item.text,
                    color = colors.fg,
                    fontFamily = FontFamily.Serif,
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
        }
    }
}

private fun bulletFor(depth: Int): String = when (depth % 3) {
    0 -> "•"
    1 -> "◦"
    else -> "▪"
}

@Composable
private fun QuoteView(block: MdBlock.Quote, colors: LlmColors) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(6.dp))
            .background(colors.sunken)
            .padding(start = 10.dp, top = 8.dp, bottom = 8.dp, end = 10.dp),
    ) {
        Box(Modifier.width(3.dp).background(colors.accent))
        Column(Modifier.padding(start = 10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            block.lines.forEach { line ->
                Text(line, color = colors.muted, fontFamily = FontFamily.Serif, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

/** F05-R5 — scrolls sideways in its own box; the message column does not. */
@Composable
private fun TableView(block: MdBlock.Table, colors: LlmColors) {
    Box(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(colors.sunken)
            .horizontalScroll(rememberScrollState())
            .testTag("md_table"),
    ) {
        Column {
            Row(Modifier.background(colors.surfaceElevated)) {
                block.header.forEachIndexed { i, cell ->
                    TableCell(cell, colors, colors.fg, bold = true, align = block.alignments.getOrElse(i) { TableAlign.LEFT })
                }
            }
            block.rows.forEach { row ->
                Row {
                    row.forEachIndexed { i, cell ->
                        TableCell(cell, colors, colors.muted, bold = false, align = block.alignments.getOrElse(i) { TableAlign.LEFT })
                    }
                }
            }
        }
    }
}

@Composable
private fun TableCell(text: AnnotatedString, colors: LlmColors, color: androidx.compose.ui.graphics.Color, bold: Boolean, align: TableAlign) {
    Text(
        text,
        color = color,
        fontFamily = FontFamily.Serif,
        style = if (bold) MaterialTheme.typography.labelLarge else MaterialTheme.typography.bodyMedium,
        textAlign = when (align) {
            TableAlign.LEFT -> androidx.compose.ui.text.style.TextAlign.Start
            TableAlign.CENTER -> androidx.compose.ui.text.style.TextAlign.Center
            TableAlign.RIGHT -> androidx.compose.ui.text.style.TextAlign.End
        },
        modifier = Modifier.width(140.dp).padding(horizontal = 10.dp, vertical = 8.dp),
    )
}

@Composable
private fun HorizontalRuleView(colors: LlmColors) {
    Box(Modifier.fillMaxWidth().height(1.dp).background(colors.line))
}

// -- Artifacts (F05-R6/R8) ---------------------------------------------------

/**
 * `svg` and `image` render as pictures, `code` as a code block, `html` as a
 * labelled placeholder (F05-R8, cut for v1 — no WebView sandbox for arbitrary
 * scripted content on the phone). A failed decode falls back to a placeholder
 * rather than a broken message (F05-R6's fifth criterion).
 */
@Composable
fun ArtifactCard(artifact: ArtifactRecord, modifier: Modifier = Modifier) {
    val colors = LlmTheme.colors
    Column(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(colors.sunken)
            .testTag("artifact_${artifact.type}"),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(artifact.type.uppercase(), color = colors.subtle, style = MaterialTheme.typography.labelSmall)
            Text(
                artifact.title ?: "Artifact",
                color = colors.muted,
                style = MaterialTheme.typography.labelMedium,
                modifier = Modifier.weight(1f),
            )
        }
        when (artifact.type) {
            "svg" -> SvgArtifactBody(artifact, colors)
            "image" -> ImageArtifactBody(artifact, colors)
            "code" -> Box(Modifier.fillMaxWidth().padding(10.dp).horizontalScroll(rememberScrollState())) {
                Text(artifact.content, color = colors.fg, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodyMedium)
            }
            "html" -> HtmlArtifactPlaceholder(colors)
            else -> HtmlArtifactPlaceholder(colors)
        }
    }
}

@Composable
private fun HtmlArtifactPlaceholder(colors: LlmColors) {
    Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("This artifact can be opened on the desktop.", color = colors.muted, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun ImageArtifactBody(artifact: ArtifactRecord, colors: LlmColors) {
    // Same encoding the composer uses for attachments (F04-R9): a
    // `data:image/…;base64,…` URL.
    val bitmap = remember(artifact.content) { decodeDataUrl(artifact.content) }
    var fullScreen by remember { mutableStateOf(false) }
    if (bitmap == null) {
        Text(
            "This image couldn't be decoded.",
            color = colors.subtle,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(12.dp),
        )
        return
    }
    Image(
        bitmap = bitmap.asImageBitmap(),
        contentDescription = artifact.title,
        contentScale = ContentScale.Fit,
        modifier = Modifier
            .fillMaxWidth()
            .height(200.dp)
            .clickable { fullScreen = true }
            .testTag("artifact_image"),
    )
    if (fullScreen) FullScreenBitmapViewer(bitmap) { fullScreen = false }
}

@Composable
private fun SvgArtifactBody(artifact: ArtifactRecord, colors: LlmColors) {
    if (artifact.content.isBlank()) {
        Text(
            "This diagram couldn't be rendered.",
            color = colors.subtle,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(12.dp),
        )
        return
    }
    var fullScreen by remember { mutableStateOf(false) }
    Box(
        Modifier
            .fillMaxWidth()
            .height(200.dp)
            .background(androidx.compose.ui.graphics.Color.White)
            .testTag("artifact_svg"),
    ) {
        SvgWebView(artifact.content, zoomable = false, modifier = Modifier.fillMaxSize())
        // A plain WebView consumes touch input for its own gesture detection
        // even with JS off, so a `.clickable` on the Box behind it never fires
        // (the WebView is a real Android View and claims the touch first).
        // This transparent overlay sits in front of it in the Compose tree and
        // catches the tap before it reaches the WebView.
        Box(Modifier.matchParentSize().clickable { fullScreen = true })
    }
    if (fullScreen) {
        Dialog(onDismissRequest = { fullScreen = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Box(Modifier.fillMaxSize().background(androidx.compose.ui.graphics.Color.Black).clickable { fullScreen = false }) {
                SvgWebView(artifact.content, zoomable = true, modifier = Modifier.fillMaxSize())
            }
        }
    }
}

/**
 * A static SVG has no interactivity to sandbox against, unlike F05-R8's
 * arbitrary HTML — so unlike that placeholder, rendering it in a plain
 * (JS-disabled) `WebView` is cheap and gives pinch-zoom for free via the
 * platform's own zoom controls, with no new dependency.
 */
@Composable
private fun SvgWebView(svg: String, zoomable: Boolean, modifier: Modifier = Modifier) {
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            WebView(ctx).apply {
                setBackgroundColor(android.graphics.Color.WHITE)
                settings.javaScriptEnabled = false
                // The SVG source is untrusted model output — `javaScriptEnabled =
                // false` stops script execution but not a network fetch from
                // `<img src>` or a CSS `url()`, so a remote `xlink:href` would
                // otherwise beacon out silently. Blocks both the thumbnail and
                // full-screen instances, since they share this factory.
                settings.blockNetworkLoads = true
                settings.setSupportZoom(zoomable)
                settings.builtInZoomControls = zoomable
                settings.displayZoomControls = false
                // Obey the viewport meta in [svgDocument] rather than assuming
                // the 980 px desktop width a WebView guesses for a page without
                // one — that guess is half of why the diagram sat off-frame.
                settings.useWideViewPort = true
                settings.loadWithOverviewMode = true
                isVerticalScrollBarEnabled = false
                isHorizontalScrollBarEnabled = false
            }
        },
        update = { webView ->
            val html = svgDocument(svg, zoomable)
            // `update` runs on every recomposition, and a reload resets the
            // user's zoom — so only reload when the document actually changed.
            if (webView.tag != html) {
                webView.tag = html
                webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
            }
        },
    )
}

/**
 * Fits the diagram to its frame.
 *
 * Schemdraw sizes its root element in **points** (`width="173.168pt"`) and puts
 * the real geometry in the `viewBox`. Nothing in the old wrapper related that
 * to the size of the frame, so a drawing wider than the phone was simply
 * cropped — and because the body centred it, the overflow went off *both*
 * edges and the left of the circuit could not be reached at any zoom. Capping
 * both dimensions at 100% and letting the viewBox supply the aspect ratio is
 * what makes it fit; `width/height:auto` is needed to stop the `pt` attributes
 * winning.
 */
private fun svgDocument(svg: String, zoomable: Boolean): String {
    val scaling = if (zoomable) "initial-scale=1,minimum-scale=1,maximum-scale=6" else "initial-scale=1,user-scalable=no"
    return """
        <html><head>
        <meta name="viewport" content="width=device-width,$scaling">
        <style>
          html,body{margin:0;height:100%;}
          body{display:flex;align-items:center;justify-content:center;}
          svg{max-width:100%;max-height:100%;width:auto;height:auto;display:block;}
        </style>
        </head><body>$svg</body></html>
    """.trimIndent()
}

/** F05-R6's fourth criterion — tap an image, get it full-screen with pinch-zoom. */
@Composable
fun FullScreenBitmapViewer(bitmap: Bitmap, onDismiss: () -> Unit) {
    var scale by remember { mutableFloatStateOf(1f) }
    var offsetX by remember { mutableFloatStateOf(0f) }
    var offsetY by remember { mutableFloatStateOf(0f) }
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Box(
            Modifier
                .fillMaxSize()
                .background(androidx.compose.ui.graphics.Color.Black)
                .pointerInput(Unit) {
                    detectTransformGestures { _, pan, zoom, _ ->
                        scale = (scale * zoom).coerceIn(1f, 6f)
                        offsetX += pan.x
                        offsetY += pan.y
                    }
                }
                .pointerInput(Unit) { detectTapGestures(onTap = { onDismiss() }) }
                .testTag("fullscreen_image"),
            contentAlignment = Alignment.Center,
        ) {
            Image(
                bitmap = bitmap.asImageBitmap(),
                contentDescription = null,
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .fillMaxSize()
                    .graphicsLayer(scaleX = scale, scaleY = scale, translationX = offsetX, translationY = offsetY),
            )
        }
    }
}

// -- Copy / share (F05-R3) ---------------------------------------------------

/** Copies the message's raw Markdown source — not the rendered text (F05-R3's first criterion). */
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
