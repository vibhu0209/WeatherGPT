package `in`.weathergpt

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
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

/** Shared spacing: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40. */
object Space {
    val xs = 4.dp
    val sm = 8.dp
    val md = 12.dp
    val lg = 16.dp
    val xl = 24.dp
    val xxl = 32.dp
    val huge = 40.dp
    val screen = 20.dp
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
fun StatusBanner(text: String, tone: BannerTone = BannerTone.INFO) {
    val (bg, fg) = when (tone) {
        BannerTone.INFO -> MaterialTheme.colorScheme.secondaryContainer to MaterialTheme.colorScheme.onSecondaryContainer
        BannerTone.WARN -> MaterialTheme.colorScheme.tertiaryContainer to MaterialTheme.colorScheme.onTertiaryContainer
        BannerTone.ERROR -> MaterialTheme.colorScheme.errorContainer to MaterialTheme.colorScheme.onErrorContainer
        BannerTone.QUIET -> MaterialTheme.colorScheme.surfaceVariant to MaterialTheme.colorScheme.onSurfaceVariant
    }
    Surface(
        color = bg,
        contentColor = fg,
        shape = MaterialTheme.shapes.small,
        modifier = Modifier.fillMaxWidth().padding(horizontal = Space.screen, vertical = Space.xs),
    ) {
        Text(text, Modifier.padding(horizontal = Space.lg, vertical = Space.md), style = MaterialTheme.typography.bodyMedium)
    }
}

enum class BannerTone { INFO, WARN, ERROR, QUIET }

fun bannerToneFor(notice: WeatherNotice): BannerTone = when (notice) {
    WeatherNotice.STALE, WeatherNotice.OFFLINE_CACHED -> BannerTone.QUIET
    WeatherNotice.CANT_CONNECT, WeatherNotice.NO_DATA, WeatherNotice.CHECK_SETTINGS -> BannerTone.WARN
    WeatherNotice.PROVIDER_DOWN, WeatherNotice.PROVIDERS_UNAVAILABLE -> BannerTone.ERROR
    WeatherNotice.NO_SAVED -> BannerTone.INFO
    WeatherNotice.NONE -> BannerTone.INFO
}

@Composable
fun WeatherMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Column(
        modifier.semantics { contentDescription = "$label $value" },
        verticalArrangement = Arrangement.spacedBy(Space.xs),
    ) {
        Text(label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun MetricRow(items: List<Pair<String, String>>, stack: Boolean) {
    Surface(
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.72f),
        shape = MaterialTheme.shapes.medium,
        tonalElevation = 0.dp,
        modifier = Modifier.fillMaxWidth(),
    ) {
        if (stack) {
            Column(Modifier.padding(horizontal = Space.lg, vertical = Space.md), verticalArrangement = Arrangement.spacedBy(Space.sm)) {
                items.forEach { (label, value) -> WeatherMetric(label, value, Modifier.fillMaxWidth()) }
            }
        } else {
            Row(Modifier.padding(horizontal = Space.lg, vertical = Space.md), horizontalArrangement = Arrangement.spacedBy(Space.md)) {
                items.forEach { (label, value) -> WeatherMetric(label, value, Modifier.weight(1f)) }
            }
        }
    }
}

@Composable
fun WeatherScoreCard(score: WeatherScore) {
    val unavailable = s(R.string.unavailable)
    val announcement = weatherScoreTalkBack(s(R.string.weather_score), score.score, score.label, unavailable)
    Surface(
        color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.35f),
        contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
        shape = MaterialTheme.shapes.medium,
        tonalElevation = 0.dp,
        modifier = Modifier.fillMaxWidth().semantics(mergeDescendants = true) { contentDescription = announcement },
    ) {
        Row(
            Modifier.padding(horizontal = Space.lg, vertical = Space.md),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Space.md),
        ) {
            Text(s(R.string.weather_score), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(
                "${score.score ?: unavailable}",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                score.label,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

private val UNCERTAINTY_ADVICE_RULES = setOf("sources_disagree", "low_forecast_confidence")

/** Drop repeated confidence/disagreement boilerplate and raw-data scaffolding from display text only. */
fun stripUncertaintyBoilerplate(text: String): String {
    var t = text.trim()
    val patterns = listOf(
        Regex("""(?im)^Weather sources disagree.*$"""),
        Regex("""(?im)^Treat this outlook as less certain\.?\s*$"""),
        Regex("""(?im)^This is a forecast, not a certainty\.?\s*$"""),
        Regex("""(?i)Models differ[^.!\n]*[.!]?"""),
        Regex("""(?i)Prefer the safer window[^.!\n]*[.!]?"""),
        Regex("""(?i)Refresh before you leave if the plan is critical\.?"""),
        Regex("""(?i)the recommended window still stands\.?"""),
        Regex("""(?i)agreement\s+\d+/100[^.!\n]*[.!]?"""),
        Regex("""(?i)Weather sources disagree[^.!\n]*[.!]?"""),
        Regex("""(?i)Treat this outlook as less certain\.?"""),
        Regex("""(?i)This is a forecast, not a certainty\.?"""),
        Regex("""(?im)^Supporting reading:.*$"""),
        Regex("""(?im)^Weather score for.*$"""),
        Regex("""(?i)\(supporting detail\)"""),
        Regex("""(?im)^The connected official service reports.*$"""),
        Regex("""(?im)^If an IMD warning is active for your area.*$"""),
        Regex("""(?im)^Supporting inputs:.*$"""),
    )
    patterns.forEach { t = it.replace(t, " ") }
    return t.replace(Regex("""[ \t]+\n"""), "\n")
        .replace(Regex("""\n{3,}"""), "\n\n")
        .replace(Regex(""" {2,}"""), " ")
        .trim()
}

fun primaryAdviceMessage(recommendations: List<Recommendation>?): String? =
    recommendations.orEmpty()
        .filter { it.rule !in UNCERTAINTY_ADVICE_RULES }
        .map { stripUncertaintyBoilerplate(it.message) }
        .firstOrNull { it.isNotBlank() }

fun shouldShowConfidenceNote(bundle: BundleDto?): Boolean {
    if (bundle == null) return false
    if (bundle.agreement == "sources_disagree") return true
    val score = bundle.confidence?.score
    return score != null && score < 75
}

@Composable
fun compactConfidenceLabel(bundle: BundleDto): String {
    val score = bundle.confidence?.score
    return s(
        when {
            score != null && score >= 75 -> R.string.confidence_compact_high
            score != null && score >= 50 -> R.string.confidence_compact_medium
            score != null -> R.string.confidence_compact_low
            bundle.agreement == "sources_disagree" -> R.string.confidence_compact_medium
            else -> R.string.confidence_compact_medium
        },
    )
}

/** One compact confidence line per screen; ⓘ expands existing disagreement/help copy. */
@Composable
fun ConfidenceNote(bundle: BundleDto, score: WeatherScore? = null, modifier: Modifier = Modifier) {
    if (!shouldShowConfidenceNote(bundle)) return
    var open by rememberSaveable(bundle.retrieved_at) { mutableStateOf(false) }
    val label = compactConfidenceLabel(bundle)
    val infoCd = s(R.string.confidence_info_cd)
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(Space.xs)) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Space.xs),
            modifier = Modifier
                .clickable { open = !open }
                .semantics { contentDescription = "$label. $infoCd" }
                .padding(vertical = Space.xs),
        ) {
            Text(
                label,
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Icon(
                Icons.Default.Info,
                contentDescription = infoCd,
                modifier = Modifier.size(18.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        AnimatedVisibility(
            visible = open,
            enter = fadeIn() + expandVertically(),
            exit = fadeOut() + shrinkVertically(),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(Space.sm)) {
                if (bundle.agreement == "sources_disagree") {
                    Text(s(R.string.disagree), style = MaterialTheme.typography.bodyMedium)
                }
                Text(s(R.string.confidence_help), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                bundle.confidence?.reasons.orEmpty().take(3).forEach {
                    Text("• $it", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                bundle.disagreement_reasons.orEmpty().take(3).forEach {
                    Text("• $it", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                score?.limiting_factors.orEmpty().take(2).forEach {
                    Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Text(s(R.string.score_disclaimer), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

/** Compact chat/home weather context — typography, not a card farm. */
@Composable
fun WeatherContextStrip(
    placeName: String?,
    temperature: Double?,
    weatherCode: Int?,
    conditionLabel: String?,
    score: Int?,
    adviceLine: String? = null,
    modifier: Modifier = Modifier,
) {
    val atmosphere = weatherAtmosphere(weatherCode)
    Surface(
        color = if (atmosphere.alpha > 0f) atmosphere else MaterialTheme.colorScheme.surface,
        shape = MaterialTheme.shapes.medium,
        modifier = modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(horizontal = Space.lg, vertical = Space.md), verticalArrangement = Arrangement.spacedBy(Space.sm)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.md)) {
                ConditionIcon(weatherCode, conditionLabel, size = 36.dp)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    if (!placeName.isNullOrBlank()) {
                        Text(placeName, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
                        temperature?.let {
                            Text("${it.toInt()}°", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
                        }
                        conditionLabel?.let {
                            Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(bottom = 2.dp))
                        }
                    }
                }
                score?.let {
                    Text(
                        String.format(s(R.string.chat_context_score), it),
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
            if (!adviceLine.isNullOrBlank()) {
                Text(adviceLine, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
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
        border = androidx.compose.foundation.BorderStroke(1.dp, colors.second.copy(alpha = 0.25f)),
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
        label = { Text(label, style = MaterialTheme.typography.labelLarge, maxLines = 1) },
        modifier = Modifier.heightIn(min = 44.dp).widthIn(max = 200.dp),
        shape = MaterialTheme.shapes.small,
        colors = AssistChipDefaults.assistChipColors(
            containerColor = MaterialTheme.colorScheme.surface,
            labelColor = MaterialTheme.colorScheme.onSurface,
        ),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline.copy(alpha = 0.4f)),
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

@Composable
fun Appear(visible: Boolean = true, content: @Composable () -> Unit) {
    AnimatedVisibility(
        visible = visible,
        enter = fadeIn(WeatherMotion.fast) + slideInVertically(animationSpec = androidx.compose.animation.core.tween(WeatherMotion.FastMs)) { it / 16 },
        exit = fadeOut(WeatherMotion.fast),
    ) { content() }
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
