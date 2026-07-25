package com.hpz.llmdockchat.feature.designlab.icons

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.unit.dp
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin

/**
 * Hand-drawn line icons for the design-lab mockups only. `material3` ships no
 * icon set on this project's classpath and `material-icons-extended` isn't a
 * dependency — adding one is a real build-file change and out of scope for a
 * proposal branch (flagged in the report instead of done silently), so this
 * is a small subset of stroke-style `ImageVector`s built the same way the
 * reference mockups draw their sprite (`docs/android/chat-app-mockups.html`),
 * just enough to replace the emoji this brief called out. Not a design
 * system — four screens' worth of glyphs.
 */
object DesignLabIcons {
    private fun strokeIcon(name: String, build: androidx.compose.ui.graphics.vector.PathBuilder.() -> Unit): ImageVector =
        ImageVector.Builder(name = name, defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f)
            .path(
                fill = null,
                stroke = SolidColor(Color.Black),
                strokeLineWidth = 1.8f,
                strokeLineCap = StrokeCap.Round,
                strokeLineJoin = StrokeJoin.Round,
                pathFillType = PathFillType.NonZero,
                pathBuilder = build,
            )
            .build()

    val Back: ImageVector by lazy {
        strokeIcon("Back") { moveTo(15f, 5f); lineTo(8f, 12f); lineTo(15f, 19f) }
    }

    val Image: ImageVector by lazy {
        strokeIcon("Image") {
            moveTo(4f, 5f); lineTo(20f, 5f); lineTo(20f, 19f); lineTo(4f, 19f); close()
            moveTo(8.2f, 10f); lineTo(9.4f, 10f)
            moveTo(5f, 17f); lineTo(9.5f, 12.5f); lineTo(13f, 16f); lineTo(16f, 13f); lineTo(19f, 16f)
        }
    }

    val Camera: ImageVector by lazy {
        strokeIcon("Camera") {
            // The body, then the viewfinder bump, then the lens as a real
            // circle. The first version left the lens as two bare moveTo calls,
            // which draw nothing — it rendered as a plain blob.
            moveTo(3f, 8.5f); lineTo(7.5f, 8.5f); lineTo(9f, 6f); lineTo(15f, 6f); lineTo(16.5f, 8.5f); lineTo(21f, 8.5f)
            lineTo(21f, 19f); lineTo(3f, 19f); close()
            moveTo(15.2f, 13.6f)
            curveTo(15.2f, 15.37f, 13.77f, 16.8f, 12f, 16.8f)
            curveTo(10.23f, 16.8f, 8.8f, 15.37f, 8.8f, 13.6f)
            curveTo(8.8f, 11.83f, 10.23f, 10.4f, 12f, 10.4f)
            curveTo(13.77f, 10.4f, 15.2f, 11.83f, 15.2f, 13.6f)
            close()
        }
    }

    val Paperclip: ImageVector by lazy {
        strokeIcon("Paperclip") {
            moveTo(16.5f, 8f)
            lineTo(9.2f, 15.3f)
            curveTo(8.2f, 16.3f, 8.2f, 17.9f, 9.2f, 18.9f)
            curveTo(10.2f, 19.9f, 11.8f, 19.9f, 12.8f, 18.9f)
            lineTo(19.2f, 12.5f)
            curveTo(21f, 10.7f, 21f, 7.8f, 19.2f, 6f)
            curveTo(17.4f, 4.2f, 14.5f, 4.2f, 12.7f, 6f)
            lineTo(6.3f, 12.4f)
        }
    }

    val Send: ImageVector by lazy {
        strokeIcon("Send") { moveTo(12f, 19f); lineTo(12f, 6f); moveTo(6f, 12f); lineTo(12f, 6f); lineTo(18f, 12f) }
    }

    val Stop: ImageVector by lazy {
        ImageVector.Builder(name = "Stop", defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f)
            .path(fill = SolidColor(Color.Black)) {
                moveTo(7f, 7f); lineTo(17f, 7f); lineTo(17f, 17f); lineTo(7f, 17f); close()
            }
            .build()
    }

    val Copy: ImageVector by lazy {
        strokeIcon("Copy") {
            moveTo(9f, 9f); lineTo(20f, 9f); lineTo(20f, 20f); lineTo(9f, 20f); close()
            moveTo(15f, 6f); lineTo(6f, 6f); lineTo(6f, 17f); lineTo(9f, 17f)
        }
    }

    val ChatBubble: ImageVector by lazy {
        strokeIcon("ChatBubble") {
            moveTo(4f, 6f)
            curveTo(4f, 4.9f, 4.9f, 4f, 6f, 4f)
            lineTo(18f, 4f)
            curveTo(19.1f, 4f, 20f, 4.9f, 20f, 6f)
            lineTo(20f, 14f)
            curveTo(20f, 15.1f, 19.1f, 16f, 18f, 16f)
            lineTo(9f, 16f)
            lineTo(4f, 20f)
            close()
        }
    }

    val Chip: ImageVector by lazy {
        strokeIcon("Chip") {
            moveTo(7f, 7f); lineTo(17f, 7f); lineTo(17f, 17f); lineTo(7f, 17f); close()
            moveTo(10f, 3f); lineTo(10f, 7f)
            moveTo(14f, 3f); lineTo(14f, 7f)
            moveTo(10f, 17f); lineTo(10f, 21f)
            moveTo(14f, 17f); lineTo(14f, 21f)
            moveTo(3f, 10f); lineTo(7f, 10f)
            moveTo(3f, 14f); lineTo(7f, 14f)
            moveTo(17f, 10f); lineTo(21f, 10f)
            moveTo(17f, 14f); lineTo(21f, 14f)
        }
    }

    val Power: ImageVector by lazy {
        strokeIcon("Power") {
            moveTo(12f, 3f); lineTo(12f, 11f)
            moveTo(6.6f, 6.6f)
            curveTo(3.1f, 10.1f, 3.1f, 15.8f, 6.6f, 19.3f)
            curveTo(10.1f, 22.8f, 15.9f, 22.8f, 19.4f, 19.3f)
            curveTo(22.9f, 15.8f, 22.9f, 10.1f, 19.4f, 6.6f)
        }
    }

    val Play: ImageVector by lazy {
        ImageVector.Builder(name = "Play", defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f)
            .path(fill = SolidColor(Color.Black)) {
                moveTo(8f, 5.5f); lineTo(18f, 12f); lineTo(8f, 18.5f); close()
            }
            .build()
    }

    val Terminal: ImageVector by lazy {
        strokeIcon("Terminal") {
            moveTo(3f, 4f); lineTo(21f, 4f); lineTo(21f, 20f); lineTo(3f, 20f); close()
            moveTo(7f, 9f); lineTo(10f, 12f); lineTo(7f, 15f)
            moveTo(13f, 15f); lineTo(17f, 15f)
        }
    }

    val MoreVertical: ImageVector by lazy {
        ImageVector.Builder(name = "MoreVertical", defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f)
            .path(fill = SolidColor(Color.Black)) {
                listOf(5.6f, 12f, 18.4f).forEach { cy ->
                    moveTo(12f, cy - 1.7f)
                    curveTo(12.94f, cy - 1.7f, 13.7f, cy - 0.94f, 13.7f, cy)
                    curveTo(13.7f, cy + 0.94f, 12.94f, cy + 1.7f, 12f, cy + 1.7f)
                    curveTo(11.06f, cy + 1.7f, 10.3f, cy + 0.94f, 10.3f, cy)
                    curveTo(10.3f, cy - 0.94f, 11.06f, cy - 1.7f, 12f, cy - 1.7f)
                    close()
                }
            }
            .build()
    }

    val ChevronLeft: ImageVector by lazy {
        strokeIcon("ChevronLeft") { moveTo(15f, 5f); lineTo(8f, 12f); lineTo(15f, 19f) }
    }

    val ChevronRight: ImageVector by lazy {
        strokeIcon("ChevronRight") { moveTo(9f, 5f); lineTo(16f, 12f); lineTo(9f, 19f) }
    }

    val ChevronDown: ImageVector by lazy {
        strokeIcon("ChevronDown") { moveTo(5f, 9f); lineTo(12f, 16f); lineTo(19f, 9f) }
    }

    val Plus: ImageVector by lazy {
        strokeIcon("Plus") { moveTo(12f, 5f); lineTo(12f, 19f); moveTo(5f, 12f); lineTo(19f, 12f) }
    }

    val Search: ImageVector by lazy {
        strokeIcon("Search") {
            moveTo(15.5f, 10.5f)
            curveTo(15.5f, 13.26f, 13.26f, 15.5f, 10.5f, 15.5f)
            curveTo(7.74f, 15.5f, 5.5f, 13.26f, 5.5f, 10.5f)
            curveTo(5.5f, 7.74f, 7.74f, 5.5f, 10.5f, 5.5f)
            curveTo(13.26f, 5.5f, 15.5f, 7.74f, 15.5f, 10.5f)
            close()
            moveTo(19.5f, 19.5f); lineTo(14.9f, 14.9f)
        }
    }

    val Trash: ImageVector by lazy {
        strokeIcon("Trash") {
            moveTo(4f, 6.5f); lineTo(20f, 6.5f)
            moveTo(9.5f, 6.5f); lineTo(9.5f, 4.5f); lineTo(14.5f, 4.5f); lineTo(14.5f, 6.5f)
            moveTo(6.5f, 6.5f); lineTo(7.4f, 20f); lineTo(16.6f, 20f); lineTo(17.5f, 6.5f)
            moveTo(10.5f, 10f); lineTo(10.5f, 16.5f)
            moveTo(13.5f, 10f); lineTo(13.5f, 16.5f)
        }
    }

    val Close: ImageVector by lazy {
        strokeIcon("Close") { moveTo(6f, 6f); lineTo(18f, 18f); moveTo(18f, 6f); lineTo(6f, 18f) }
    }

    val Sparkle: ImageVector by lazy {
        strokeIcon("Sparkle") {
            moveTo(12f, 3f); lineTo(13.3f, 9.2f); lineTo(19.5f, 10.5f); lineTo(13.3f, 11.8f); lineTo(12f, 18f); lineTo(10.7f, 11.8f); lineTo(4.5f, 10.5f); lineTo(10.7f, 9.2f); close()
        }
    }
}
