package `in`.weathergpt

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** Calm sky / leaf palette — readable outdoors, not purple “AI” chrome. */
val WeatherLight = lightColorScheme(
    primary = Color(0xFF1B6B5A),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD4F0E6),
    onPrimaryContainer = Color(0xFF0A3D32),
    secondary = Color(0xFF3D6B8A),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFD7EAF6),
    onSecondaryContainer = Color(0xFF163447),
    tertiary = Color(0xFFB86A1C),
    tertiaryContainer = Color(0xFFFFE4C2),
    onTertiaryContainer = Color(0xFF4A2800),
    background = Color(0xFFF2F5F3),
    surface = Color(0xFFFBFCFB),
    surfaceVariant = Color(0xFFE4EDE8),
    onSurface = Color(0xFF152922),
    onSurfaceVariant = Color(0xFF3F534B),
    outline = Color(0xFF8AA097),
    errorContainer = Color(0xFFFFDAD6),
    onErrorContainer = Color(0xFF410002),
)

val WeatherDark = darkColorScheme(
    primary = Color(0xFF8FD6C0),
    onPrimary = Color(0xFF00382D),
    primaryContainer = Color(0xFF1A4F42),
    onPrimaryContainer = Color(0xFFB8F0DC),
    secondary = Color(0xFF9FCBE6),
    onSecondary = Color(0xFF0C3042),
    secondaryContainer = Color(0xFF254556),
    onSecondaryContainer = Color(0xFFD4ECF8),
    tertiary = Color(0xFFFFB77A),
    tertiaryContainer = Color(0xFF5C3A12),
    onTertiaryContainer = Color(0xFFFFE0B8),
    background = Color(0xFF0E1613),
    surface = Color(0xFF141E1A),
    surfaceVariant = Color(0xFF2A3832),
    onSurface = Color(0xFFE2EEE8),
    onSurfaceVariant = Color(0xFFBCC9C1),
    outline = Color(0xFF6F8278),
    errorContainer = Color(0xFF8C1D18),
    onErrorContainer = Color(0xFFFFDAD6),
)

/** Slightly tighter radii — cards only when interaction needs them. */
val WeatherShapes = Shapes(
    extraSmall = RoundedCornerShape(6.dp),
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(14.dp),
    large = RoundedCornerShape(18.dp),
    extraLarge = RoundedCornerShape(22.dp),
)

/**
 * Editorial hierarchy: expressive temperature, calm conversation, quiet metadata.
 * Weights carry contrast — sizes stay disciplined.
 */
val WeatherTypography = Typography(
    displayLarge = TextStyle(
        fontSize = 60.sp,
        lineHeight = 66.sp,
        fontWeight = FontWeight.Light,
        letterSpacing = (-0.5).sp,
    ),
    displayMedium = TextStyle(
        fontSize = 44.sp,
        lineHeight = 50.sp,
        fontWeight = FontWeight.Light,
        letterSpacing = (-0.25).sp,
    ),
    headlineSmall = TextStyle(fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.SemiBold),
    titleLarge = TextStyle(fontSize = 20.sp, lineHeight = 26.sp, fontWeight = FontWeight.SemiBold),
    titleMedium = TextStyle(fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.Medium),
    bodyLarge = TextStyle(fontSize = 17.sp, lineHeight = 26.sp, fontWeight = FontWeight.Normal),
    bodyMedium = TextStyle(fontSize = 15.sp, lineHeight = 22.sp, fontWeight = FontWeight.Normal),
    labelLarge = TextStyle(fontSize = 13.sp, lineHeight = 18.sp, fontWeight = FontWeight.Medium, letterSpacing = 0.2.sp),
    labelMedium = TextStyle(fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.Medium),
    labelSmall = TextStyle(fontSize = 11.sp, lineHeight = 14.sp, fontWeight = FontWeight.Medium, letterSpacing = 0.3.sp),
)

/** Shared motion — purposeful, never theatrical. */
object WeatherMotion {
    val fast = tween<Float>(durationMillis = 110, easing = FastOutSlowInEasing)
    val normal = tween<Float>(durationMillis = 160, easing = FastOutSlowInEasing)
    val expand = tween<Int>(durationMillis = 200, easing = FastOutSlowInEasing)
    const val FastMs = 110
    const val NormalMs = 160
    const val ExpandMs = 200
}

@Composable
fun WeatherTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = if (darkTheme) WeatherDark else WeatherLight,
        typography = WeatherTypography,
        shapes = WeatherShapes,
        content = content,
    )
}
