package com.hpz.llmdockchat.core.ui

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp

@Composable
fun BrandMark(modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "brand_mark")
    val glowAlpha by transition.animateFloat(
        initialValue = 0.14f,
        targetValue = 0.26f,
        animationSpec = infiniteRepeatable(
            animation = tween(1800, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "brand_mark_glow",
    )

    Canvas(modifier = modifier) {
        val side = size.minDimension * 0.72f
        val left = (size.width - side) / 2f
        val top = (size.height - side) / 2f

        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(
                    Color(0xFF3B82F6).copy(alpha = glowAlpha),
                    Color.Transparent,
                ),
                center = center,
                radius = size.minDimension / 2f,
            ),
            radius = size.minDimension / 2f,
        )
        drawRoundRect(
            brush = Brush.linearGradient(
                colors = listOf(
                    Color(0xFF172554),
                    Color(0xFF1D4ED8),
                    Color(0xFF3B82F6),
                ),
                start = Offset(left, top),
                end = Offset(left + side, top + side),
            ),
            topLeft = Offset(left, top),
            size = Size(side, side),
            cornerRadius = CornerRadius(side * 0.24f),
        )

        fun x(value: Float) = left + side * value / 108f
        fun y(value: Float) = top + side * value / 108f

        val monogram = Path().apply {
            moveTo(x(31f), y(30f))
            lineTo(x(31f), y(78f))
            lineTo(x(44f), y(78f))
            moveTo(x(47f), y(30f))
            lineTo(x(47f), y(78f))
            lineTo(x(57f), y(78f))
            cubicTo(x(72f), y(78f), x(81f), y(68.5f), x(81f), y(54f))
            cubicTo(x(81f), y(39.5f), x(72f), y(30f), x(57f), y(30f))
            close()
        }
        drawPath(
            path = monogram,
            color = Color.White,
            style = Stroke(
                width = side * 6.5f / 108f,
                cap = StrokeCap.Round,
                join = StrokeJoin.Round,
            ),
        )
    }
}
