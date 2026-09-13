package `in`.weathergpt

import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AcUnit
import androidx.compose.material.icons.filled.Cloud
import androidx.compose.material.icons.filled.Thunderstorm
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material.icons.filled.WbCloudy
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material.icons.outlined.BlurOn
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** Minimal weather glyph language — Material vectors, not emoji. */
enum class WeatherGlyph {
    CLEAR, CLOUDY, FOG, DRIZZLE, RAIN, SNOW, SHOWERS, THUNDER, UNKNOWN
}

fun weatherGlyph(code: Int?): WeatherGlyph = when (code) {
    0 -> WeatherGlyph.CLEAR
    1, 2, 3 -> WeatherGlyph.CLOUDY
    45, 48 -> WeatherGlyph.FOG
    51, 53, 55, 56, 57 -> WeatherGlyph.DRIZZLE
    61, 63, 65, 66, 67 -> WeatherGlyph.RAIN
    71, 73, 75, 77 -> WeatherGlyph.SNOW
    80, 81, 82, 85, 86 -> WeatherGlyph.SHOWERS
    95, 96, 99 -> WeatherGlyph.THUNDER
    else -> WeatherGlyph.UNKNOWN
}

fun weatherGlyphIcon(glyph: WeatherGlyph): ImageVector = when (glyph) {
    WeatherGlyph.CLEAR -> Icons.Default.WbSunny
    WeatherGlyph.CLOUDY -> Icons.Default.WbCloudy
    WeatherGlyph.FOG -> Icons.Outlined.BlurOn
    WeatherGlyph.DRIZZLE -> Icons.Default.WaterDrop
    WeatherGlyph.RAIN -> Icons.Default.WaterDrop
    WeatherGlyph.SNOW -> Icons.Default.AcUnit
    WeatherGlyph.SHOWERS -> Icons.Default.WaterDrop
    WeatherGlyph.THUNDER -> Icons.Default.Thunderstorm
    WeatherGlyph.UNKNOWN -> Icons.Default.Cloud
}

/** Very subtle surface atmosphere from conditions — never a wallpaper. */
@Composable
fun weatherAtmosphere(code: Int?): Color {
    val scheme = MaterialTheme.colorScheme
    return when (weatherGlyph(code)) {
        WeatherGlyph.CLEAR -> scheme.tertiaryContainer.copy(alpha = 0.28f)
        WeatherGlyph.RAIN, WeatherGlyph.SHOWERS, WeatherGlyph.DRIZZLE -> scheme.secondaryContainer.copy(alpha = 0.35f)
        WeatherGlyph.THUNDER -> scheme.errorContainer.copy(alpha = 0.22f)
        WeatherGlyph.SNOW, WeatherGlyph.FOG -> scheme.surfaceVariant.copy(alpha = 0.55f)
        WeatherGlyph.CLOUDY -> scheme.primaryContainer.copy(alpha = 0.22f)
        WeatherGlyph.UNKNOWN -> Color.Transparent
    }
}

@Composable
fun ConditionIcon(
    code: Int?,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    size: Dp = 28.dp,
    tint: Color = MaterialTheme.colorScheme.primary,
) {
    Icon(
        imageVector = weatherGlyphIcon(weatherGlyph(code)),
        contentDescription = contentDescription,
        modifier = modifier.size(size),
        tint = tint,
    )
}
