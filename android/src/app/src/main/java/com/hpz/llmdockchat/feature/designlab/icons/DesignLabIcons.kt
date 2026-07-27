package com.hpz.llmdockchat.feature.designlab.icons

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathBuilder
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.unit.dp

object DesignLabIcons {
    private fun lineIcon(name: String, build: PathBuilder.() -> Unit): ImageVector =
        ImageVector.Builder(
            name = name,
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f,
        )
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

    private fun fillIcon(name: String, build: PathBuilder.() -> Unit): ImageVector =
        ImageVector.Builder(
            name = name,
            defaultWidth = 24.dp,
            defaultHeight = 24.dp,
            viewportWidth = 24f,
            viewportHeight = 24f,
        )
            .path(
                fill = SolidColor(Color.Black),
                pathFillType = PathFillType.NonZero,
                pathBuilder = build,
            )
            .build()

    private fun PathBuilder.circle(cx: Float, cy: Float, radius: Float) {
        moveTo(cx + radius, cy)
        arcTo(radius, radius, 0f, true, true, cx - radius, cy)
        arcTo(radius, radius, 0f, true, true, cx + radius, cy)
        close()
    }

    private fun PathBuilder.roundedRect(
        left: Float,
        top: Float,
        right: Float,
        bottom: Float,
        radius: Float,
    ) {
        moveTo(left + radius, top)
        lineTo(right - radius, top)
        arcTo(radius, radius, 0f, false, true, right, top + radius)
        lineTo(right, bottom - radius)
        arcTo(radius, radius, 0f, false, true, right - radius, bottom)
        lineTo(left + radius, bottom)
        arcTo(radius, radius, 0f, false, true, left, bottom - radius)
        lineTo(left, top + radius)
        arcTo(radius, radius, 0f, false, true, left + radius, top)
        close()
    }

    val Back: ImageVector by lazy {
        lineIcon("Back") {
            moveTo(15f, 5f)
            lineTo(8f, 12f)
            lineTo(15f, 19f)
        }
    }

    val Image: ImageVector by lazy {
        lineIcon("Image") {
            roundedRect(3f, 4f, 21f, 20f, 2f)
            circle(8.5f, 9.5f, 1.5f)
            moveTo(4f, 18f)
            lineTo(9f, 13f)
            lineTo(13f, 17f)
            lineTo(16f, 14f)
            lineTo(20f, 18f)
        }
    }

    val Camera: ImageVector by lazy {
        lineIcon("Camera") {
            moveTo(5f, 7f)
            lineTo(7.5f, 7f)
            lineTo(9f, 5f)
            lineTo(15f, 5f)
            lineTo(16.5f, 7f)
            lineTo(19f, 7f)
            arcTo(2f, 2f, 0f, false, true, 21f, 9f)
            lineTo(21f, 18f)
            arcTo(2f, 2f, 0f, false, true, 19f, 20f)
            lineTo(5f, 20f)
            arcTo(2f, 2f, 0f, false, true, 3f, 18f)
            lineTo(3f, 9f)
            arcTo(2f, 2f, 0f, false, true, 5f, 7f)
            close()
            circle(12f, 13f, 3.5f)
        }
    }

    val Paperclip: ImageVector by lazy {
        lineIcon("Paperclip") {
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
        lineIcon("Send") {
            moveTo(12f, 19f)
            lineTo(12f, 6f)
            moveTo(6f, 12f)
            lineTo(12f, 6f)
            lineTo(18f, 12f)
        }
    }

    val Stop: ImageVector by lazy {
        fillIcon("Stop") {
            roundedRect(7f, 7f, 17f, 17f, 2f)
        }
    }

    val Copy: ImageVector by lazy {
        lineIcon("Copy") {
            roundedRect(8f, 8f, 20f, 20f, 2f)
            moveTo(16f, 5f)
            lineTo(6f, 5f)
            arcTo(2f, 2f, 0f, false, false, 4f, 7f)
            lineTo(4f, 17f)
        }
    }

    val ChatBubble: ImageVector by lazy {
        lineIcon("ChatBubble") {
            moveTo(6f, 4f)
            lineTo(18f, 4f)
            arcTo(2f, 2f, 0f, false, true, 20f, 6f)
            lineTo(20f, 14f)
            arcTo(2f, 2f, 0f, false, true, 18f, 16f)
            lineTo(9f, 16f)
            lineTo(4f, 20f)
            lineTo(4f, 6f)
            arcTo(2f, 2f, 0f, false, true, 6f, 4f)
            close()
        }
    }

    val Chip: ImageVector by lazy {
        lineIcon("Chip") {
            roundedRect(7f, 7f, 17f, 17f, 2f)
            moveTo(10f, 3f)
            lineTo(10f, 7f)
            moveTo(14f, 3f)
            lineTo(14f, 7f)
            moveTo(10f, 17f)
            lineTo(10f, 21f)
            moveTo(14f, 17f)
            lineTo(14f, 21f)
            moveTo(3f, 10f)
            lineTo(7f, 10f)
            moveTo(3f, 14f)
            lineTo(7f, 14f)
            moveTo(17f, 10f)
            lineTo(21f, 10f)
            moveTo(17f, 14f)
            lineTo(21f, 14f)
        }
    }

    val Cog: ImageVector by lazy {
        fillIcon("Cog") {
            moveTo(19.5f, 12f)
            curveToRelative(0f, -0.23f, -0.01f, -0.45f, -0.03f, -0.68f)
            lineToRelative(1.86f, -1.41f)
            curveToRelative(0.4f, -0.3f, 0.51f, -0.86f, 0.26f, -1.3f)
            lineToRelative(-1.87f, -3.23f)
            curveToRelative(-0.25f, -0.44f, -0.79f, -0.62f, -1.25f, -0.42f)
            lineToRelative(-2.15f, 0.91f)
            curveToRelative(-0.37f, -0.26f, -0.76f, -0.49f, -1.17f, -0.68f)
            lineToRelative(-0.29f, -2.31f)
            curveTo(14.8f, 2.38f, 14.37f, 2f, 13.87f, 2f)
            horizontalLineTo(10.14f)
            curveTo(9.63f, 2f, 9.2f, 2.38f, 9.14f, 2.88f)
            lineTo(8.85f, 5.19f)
            curveToRelative(-0.41f, 0.19f, -0.8f, 0.42f, -1.17f, 0.68f)
            lineTo(5.53f, 4.96f)
            curveToRelative(-0.46f, -0.2f, -1f, -0.02f, -1.25f, 0.42f)
            lineTo(2.41f, 8.62f)
            curveToRelative(-0.25f, 0.44f, -0.14f, 0.99f, 0.26f, 1.3f)
            lineToRelative(1.86f, 1.41f)
            curveTo(4.51f, 11.55f, 4.5f, 11.77f, 4.5f, 12f)
            reflectiveCurveToRelative(0.01f, 0.45f, 0.03f, 0.68f)
            lineToRelative(-1.86f, 1.41f)
            curveToRelative(-0.4f, 0.3f, -0.51f, 0.86f, -0.26f, 1.3f)
            lineToRelative(1.87f, 3.23f)
            curveToRelative(0.25f, 0.44f, 0.79f, 0.62f, 1.25f, 0.42f)
            lineToRelative(2.15f, -0.91f)
            curveToRelative(0.37f, 0.26f, 0.76f, 0.49f, 1.17f, 0.68f)
            lineToRelative(0.29f, 2.31f)
            curveTo(9.2f, 21.62f, 9.63f, 22f, 10.13f, 22f)
            horizontalLineToRelative(3.73f)
            curveToRelative(0.5f, 0f, 0.93f, -0.38f, 0.99f, -0.88f)
            lineToRelative(0.29f, -2.31f)
            curveToRelative(0.41f, -0.19f, 0.8f, -0.42f, 1.17f, -0.68f)
            lineToRelative(2.15f, 0.91f)
            curveToRelative(0.46f, 0.2f, 1f, 0.02f, 1.25f, -0.42f)
            lineToRelative(1.87f, -3.23f)
            curveToRelative(0.25f, -0.44f, 0.14f, -0.99f, -0.26f, -1.3f)
            lineToRelative(-1.86f, -1.41f)
            curveTo(19.49f, 12.45f, 19.5f, 12.23f, 19.5f, 12f)
            close()
            moveTo(12.04f, 15.5f)
            curveToRelative(-1.93f, 0f, -3.5f, -1.57f, -3.5f, -3.5f)
            reflectiveCurveToRelative(1.57f, -3.5f, 3.5f, -3.5f)
            reflectiveCurveToRelative(3.5f, 1.57f, 3.5f, 3.5f)
            reflectiveCurveTo(13.97f, 15.5f, 12.04f, 15.5f)
            close()
        }
    }

    val Power: ImageVector by lazy {
        lineIcon("Power") {
            moveTo(12f, 3f)
            lineTo(12f, 11f)
            moveTo(6.35f, 6.35f)
            curveTo(3.23f, 9.47f, 3.23f, 14.53f, 6.35f, 17.65f)
            curveTo(9.47f, 20.77f, 14.53f, 20.77f, 17.65f, 17.65f)
            curveTo(20.77f, 14.53f, 20.77f, 9.47f, 17.65f, 6.35f)
        }
    }

    val Play: ImageVector by lazy {
        fillIcon("Play") {
            moveTo(8f, 6.82f)
            verticalLineToRelative(10.36f)
            curveToRelative(0f, 0.79f, 0.87f, 1.27f, 1.54f, 0.84f)
            lineToRelative(8.14f, -5.18f)
            curveToRelative(0.62f, -0.39f, 0.62f, -1.29f, 0f, -1.69f)
            lineTo(9.54f, 5.98f)
            curveTo(8.87f, 5.55f, 8f, 6.03f, 8f, 6.82f)
            close()
        }
    }

    val Terminal: ImageVector by lazy {
        lineIcon("Terminal") {
            roundedRect(3f, 4f, 21f, 20f, 2f)
            moveTo(7f, 9f)
            lineTo(10f, 12f)
            lineTo(7f, 15f)
            moveTo(13f, 15f)
            lineTo(17f, 15f)
        }
    }

    val MoreVertical: ImageVector by lazy {
        fillIcon("MoreVertical") {
            circle(12f, 5f, 1.5f)
            circle(12f, 12f, 1.5f)
            circle(12f, 19f, 1.5f)
        }
    }

    val ChevronLeft: ImageVector by lazy {
        lineIcon("ChevronLeft") {
            moveTo(15f, 5f)
            lineTo(8f, 12f)
            lineTo(15f, 19f)
        }
    }

    val ChevronRight: ImageVector by lazy {
        lineIcon("ChevronRight") {
            moveTo(9f, 5f)
            lineTo(16f, 12f)
            lineTo(9f, 19f)
        }
    }

    val ChevronDown: ImageVector by lazy {
        lineIcon("ChevronDown") {
            moveTo(5f, 9f)
            lineTo(12f, 16f)
            lineTo(19f, 9f)
        }
    }

    val Plus: ImageVector by lazy {
        lineIcon("Plus") {
            moveTo(12f, 5f)
            lineTo(12f, 19f)
            moveTo(5f, 12f)
            lineTo(19f, 12f)
        }
    }

    val Search: ImageVector by lazy {
        lineIcon("Search") {
            circle(10.5f, 10.5f, 5.5f)
            moveTo(19.5f, 19.5f)
            lineTo(14.4f, 14.4f)
        }
    }

    val Trash: ImageVector by lazy {
        lineIcon("Trash") {
            moveTo(5f, 7f)
            lineTo(19f, 7f)
            moveTo(10f, 7f)
            lineTo(10f, 5f)
            lineTo(14f, 5f)
            lineTo(14f, 7f)
            moveTo(7f, 7f)
            lineTo(8f, 20f)
            lineTo(16f, 20f)
            lineTo(17f, 7f)
            moveTo(10.5f, 11f)
            lineTo(10.5f, 16.5f)
            moveTo(13.5f, 11f)
            lineTo(13.5f, 16.5f)
        }
    }

    val Close: ImageVector by lazy {
        lineIcon("Close") {
            moveTo(6f, 6f)
            lineTo(18f, 18f)
            moveTo(18f, 6f)
            lineTo(6f, 18f)
        }
    }

    val Sparkle: ImageVector by lazy {
        fillIcon("Sparkle") {
            moveTo(19.46f, 8f)
            lineToRelative(0.79f, -1.75f)
            lineTo(22f, 5.46f)
            curveToRelative(0.39f, -0.18f, 0.39f, -0.73f, 0f, -0.91f)
            lineToRelative(-1.75f, -0.79f)
            lineTo(19.46f, 2f)
            curveToRelative(-0.18f, -0.39f, -0.73f, -0.39f, -0.91f, 0f)
            lineToRelative(-0.79f, 1.75f)
            lineTo(16f, 4.54f)
            curveToRelative(-0.39f, 0.18f, -0.39f, 0.73f, 0f, 0.91f)
            lineToRelative(1.75f, 0.79f)
            lineTo(18.54f, 8f)
            curveTo(18.72f, 8.39f, 19.28f, 8.39f, 19.46f, 8f)
            close()
            moveTo(11.5f, 9.5f)
            lineTo(9.91f, 6f)
            curveTo(9.56f, 5.22f, 8.44f, 5.22f, 8.09f, 6f)
            lineTo(6.5f, 9.5f)
            lineTo(3f, 11.09f)
            curveToRelative(-0.78f, 0.36f, -0.78f, 1.47f, 0f, 1.82f)
            lineToRelative(3.5f, 1.59f)
            lineTo(8.09f, 18f)
            curveToRelative(0.36f, 0.78f, 1.47f, 0.78f, 1.82f, 0f)
            lineToRelative(1.59f, -3.5f)
            lineToRelative(3.5f, -1.59f)
            curveToRelative(0.78f, -0.36f, 0.78f, -1.47f, 0f, -1.82f)
            lineTo(11.5f, 9.5f)
            close()
            moveTo(18.54f, 16f)
            lineToRelative(-0.79f, 1.75f)
            lineTo(16f, 18.54f)
            curveToRelative(-0.39f, 0.18f, -0.39f, 0.73f, 0f, 0.91f)
            lineToRelative(1.75f, 0.79f)
            lineTo(18.54f, 22f)
            curveToRelative(0.18f, 0.39f, 0.73f, 0.39f, 0.91f, 0f)
            lineToRelative(0.79f, -1.75f)
            lineTo(22f, 19.46f)
            curveToRelative(0.39f, -0.18f, 0.39f, -0.73f, 0f, -0.91f)
            lineToRelative(-1.75f, -0.79f)
            lineTo(19.46f, 16f)
            curveTo(19.28f, 15.61f, 18.72f, 15.61f, 18.54f, 16f)
            close()
        }
    }
}
