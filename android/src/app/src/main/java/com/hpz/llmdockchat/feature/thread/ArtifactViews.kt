package com.hpz.llmdockchat.feature.thread

import android.webkit.WebView
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.hpz.llmdockchat.core.attachment.decodeDataUrl
import com.hpz.llmdockchat.core.ui.render.FullScreenBitmapViewer
import com.hpz.llmdockchat.core.ui.theme.LlmColors
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.core.ui.theme.MonoFontFamily
import com.hpz.llmdockchat.data.model.ArtifactRecord
import kotlin.math.max

/**
 * `svg` and `image` render as pictures, `code` as a code block, `html` as a
 * labelled placeholder (cut: no WebView sandbox for arbitrary
 * scripted content on the phone). A failed decode falls back to a placeholder
 * rather than a broken message.
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
                Text(artifact.content, color = colors.fg, fontFamily = MonoFontFamily, style = MaterialTheme.typography.bodyMedium)
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
    // Same encoding the composer uses for attachments: a
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
 * A static SVG has no interactivity to sandbox against, unlike arbitrary
 * HTML — so unlike that placeholder, rendering it in a plain
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
