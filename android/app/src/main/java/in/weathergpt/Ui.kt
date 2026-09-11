package `in`.weathergpt

import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

/** Shared spacing scale: 4 / 8 / 12 / 16 / 24 / 32. */
object Space {
    val xs = 4.dp
    val sm = 8.dp
    val md = 12.dp
    val lg = 16.dp
    val xl = 24.dp
    val xxl = 32.dp
    val screen = 16.dp
    val touch = 52.dp
}

@Composable
fun SectionHeader(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.headlineSmall,
        modifier = Modifier.padding(top = Space.sm).semantics { heading() },
    )
}

@Composable
fun StatusBanner(text: String) {
    Surface(
        color = MaterialTheme.colorScheme.secondaryContainer,
        contentColor = MaterialTheme.colorScheme.onSecondaryContainer,
        shape = MaterialTheme.shapes.small,
        modifier = Modifier.fillMaxWidth().padding(horizontal = Space.screen, vertical = Space.xs),
    ) {
        Text(text, Modifier.padding(horizontal = Space.lg, vertical = Space.md), style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
fun WeatherMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier.semantics { contentDescription = "$label $value" }, verticalArrangement = Arrangement.spacedBy(Space.xs)) {
        Text(label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.titleLarge)
    }
}

@Composable
fun WeatherScoreCard(score: WeatherScore) {
    val unavailable = s(R.string.unavailable)
    val announcement = weatherScoreTalkBack(s(R.string.weather_score), score.score, score.label, unavailable)
    val stackLabel = LocalDensity.current.fontScale >= 1.5f
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = MaterialTheme.shapes.medium,
        tonalElevation = 1.dp,
        modifier = Modifier.fillMaxWidth().semantics(mergeDescendants = true) { contentDescription = announcement },
    ) {
        Column(Modifier.padding(Space.lg), verticalArrangement = Arrangement.spacedBy(Space.sm)) {
            Text(s(R.string.weather_score), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (stackLabel) {
                Column(verticalArrangement = Arrangement.spacedBy(Space.xs)) {
                    Text("${score.score ?: unavailable}", style = MaterialTheme.typography.displayMedium)
                    Text(score.label, style = MaterialTheme.typography.titleMedium)
                }
            } else {
                Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(Space.md)) {
                    Text("${score.score ?: unavailable}", style = MaterialTheme.typography.displayMedium)
                    Text(score.label, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f).padding(bottom = Space.sm))
                }
            }
            score.limiting_factors.orEmpty().take(2).forEach {
                Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Text(s(R.string.score_disclaimer), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
fun AlertSummary(alert: OfficialAlert, expanded: Boolean, onToggle: () -> Unit) {
    val colors = when (alertLevel(alert.severity)) {
        AlertLevel.RED -> MaterialTheme.colorScheme.errorContainer to MaterialTheme.colorScheme.onErrorContainer
        AlertLevel.ORANGE -> MaterialTheme.colorScheme.tertiaryContainer to MaterialTheme.colorScheme.onTertiaryContainer
        AlertLevel.YELLOW -> MaterialTheme.colorScheme.secondaryContainer to MaterialTheme.colorScheme.onSecondaryContainer
    }
    val mark = when (alertLevel(alert.severity)) {
        AlertLevel.RED -> "●"
        AlertLevel.ORANGE -> "▲"
        AlertLevel.YELLOW -> "■"
    }
    val severityLabel = titledSeverity(alert.severity)
    val warningLabel = s(R.string.official_warning)
    val announcement = officialWarningTalkBack(warningLabel, alert.severity, alert.headline, alert.instruction)
    Surface(
        color = colors.first,
        contentColor = colors.second,
        shape = MaterialTheme.shapes.medium,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(Space.lg), verticalArrangement = Arrangement.spacedBy(Space.sm)) {
            Column(
                Modifier.semantics(mergeDescendants = true) {
                    liveRegion = LiveRegionMode.Assertive
                    contentDescription = announcement
                },
                verticalArrangement = Arrangement.spacedBy(Space.sm),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
                    Icon(Icons.Default.Warning, contentDescription = null, modifier = Modifier.size(22.dp))
                    Text("$mark $warningLabel · $severityLabel", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                }
                Text(alert.headline, style = MaterialTheme.typography.titleLarge)
                val issuer = alert.sender?.takeIf { it.isNotBlank() }
                val until = alert.expires?.let { "${s(R.string.expires)} $it" }
                Text(listOfNotNull(issuer, until).joinToString(" · "), style = MaterialTheme.typography.bodyMedium)
                if (expanded) {
                    alert.description?.let { Text(it, style = MaterialTheme.typography.bodyLarge) }
                    alert.instruction?.let { Text(it, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium) }
                    Text("$severityLabel · ${titledSeverity(alert.certainty)}", style = MaterialTheme.typography.bodyMedium)
                }
            }
            TextButton(onClick = onToggle, modifier = Modifier.heightIn(min = Space.touch)) {
                Text(s(if (expanded) R.string.hide_details else R.string.show_details))
            }
        }
    }
}

@Composable
fun SuggestionChip(label: String, enabled: Boolean, onClick: () -> Unit) {
    AssistChip(
        onClick = onClick,
        enabled = enabled,
        label = { Text(label, style = MaterialTheme.typography.labelLarge, maxLines = 3) },
        modifier = Modifier.heightIn(min = 44.dp),
        shape = MaterialTheme.shapes.small,
    )
}

@Composable
fun PrimaryWeatherButton(label: String, icon: ImageVector? = null, onClick: () -> Unit, enabled: Boolean = true, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().heightIn(min = Space.touch),
        shape = MaterialTheme.shapes.medium,
        contentPadding = PaddingValues(horizontal = Space.lg, vertical = Space.md),
        elevation = ButtonDefaults.buttonElevation(defaultElevation = 0.dp, pressedElevation = 1.dp),
    ) {
        if (icon != null) {
            Icon(icon, null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(Space.sm))
        }
        Text(label, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center, maxLines = 3)
    }
}

@Composable
fun QuietButton(label: String, icon: ImageVector? = null, onClick: () -> Unit, enabled: Boolean = true) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier.fillMaxWidth().heightIn(min = Space.touch),
        shape = MaterialTheme.shapes.medium,
    ) {
        if (icon != null) {
            Icon(icon, null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(Space.sm))
        }
        Text(label, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center, maxLines = 3)
    }
}

fun formatWindKmh(windMs: Double?, locale: java.util.Locale): String? =
    windMs?.let { String.format(locale, "%.0f", it * MS_TO_KMH) }

private const val MS_TO_KMH = 3.6

fun nearestHour(bundle: BundleDto): Hour? {
    val now = java.time.Instant.now().epochSecond
    return bundle.hourly.minByOrNull { kotlin.math.abs(java.time.Instant.parse(it.time).epochSecond - now) }
}

fun ageMinutes(retrievedAt: String): Long =
    java.time.Duration.between(java.time.Instant.parse(retrievedAt), java.time.Instant.now()).toMinutes().coerceAtLeast(0)
