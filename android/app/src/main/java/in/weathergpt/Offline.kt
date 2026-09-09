package `in`.weathergpt

import java.time.*

enum class FreshnessState { FRESH, AGING, STALE }
object Freshness {
    fun weather(retrievedAt:String,now:Instant=Instant.now()):FreshnessState {
        val minutes=Duration.between(Instant.parse(retrievedAt),now).toMinutes()
        return when { minutes<=60 -> FreshnessState.FRESH; minutes<=180 -> FreshnessState.AGING; else -> FreshnessState.STALE }
    }
    fun officialAlert(retrievedAt:String,expires:String?,now:Instant=Instant.now()):FreshnessState {
        if(expires==null || runCatching{Instant.parse(expires)<=now}.getOrDefault(true)) return FreshnessState.STALE
        return if(Duration.between(Instant.parse(retrievedAt),now).toMinutes()<=15) FreshnessState.FRESH else FreshnessState.AGING
    }
    fun climate(retrievedAt:String,now:Instant=Instant.now())=if(Duration.between(Instant.parse(retrievedAt),now).toDays()<=7) FreshnessState.FRESH else FreshnessState.STALE
}

object Offline {
    fun answer(text:String,b:BundleDto?,offset:Int,language:String="en"):Pair<String,Int> {
        val q=text.lowercase()
        val hi=language=="hi"
        val day=when { listOf("tomorrow","kal","कल").any { q.contains(it) } -> 1; listOf("today","आज").any { q.contains(it) } -> 0; else -> offset }
        if(b==null) return (if(hi) "अभी मौसम सहेजा नहीं गया है। इंटरनेट से जुड़कर पहले मौसम डाउनलोड करें।" else "No saved forecast yet. Connect to the internet and download your weather first.") to day
        val downloaded=Instant.parse(b.retrieved_at).atZone(ZoneId.of(b.location.timezone)).format(java.time.format.DateTimeFormatter.ofPattern("d MMM, h:mm a",java.util.Locale.forLanguageTag(language)))
        val intro=if(hi) "सहेजा मौसम: ${downloaded}। जानकारी बदल सकती है।\n\n" else "Saved forecast from ${downloaded}. Conditions may have changed.\n\n"
        if(listOf("warning","alert","चेतावनी").any{q.contains(it)}) {
            val active=b.official_alerts.orEmpty().filter { alert->alert.expires?.let { runCatching { Instant.parse(it)>Instant.now() }.getOrDefault(false) }==true }
            if(active.isNotEmpty()) {
                val warnings=active.joinToString("\n\n") { alert->
                    val instruction=alert.instruction?:alert.description?:""
                    if(hi) "पहले डाउनलोड की गई आधिकारिक चेतावनी: ${alert.headline}। $instruction समाप्ति: ${alert.expires}।"
                    else "Previously downloaded official warning: ${alert.headline}. $instruction Expires: ${alert.expires}."
                }
                return (intro+warnings+"\n\n"+(if(hi) "नई चेतावनियों और बदलावों के लिए इंटरनेट चाहिए।" else "New warnings and updates require an internet connection.")) to day
            }
            return (intro+(if(hi) "नई चेतावनियों के लिए इंटरनेट चाहिए। आधिकारिक चेतावनी उपलब्धता पता नहीं है। बाहर जाने से पहले IMD की चेतावनी देखें।" else "New warnings need an internet connection. Official warning availability is unknown. Check IMD before going out.")) to day
        }
        if(!listOf("weather","rain","temperature","wind","today","tomorrow","morning","evening","afternoon","मौसम","बारिश","कल","आज","सुबह","शाम").any{q.contains(it)}) return (intro+(if(hi) "मैं आज या कल का सहेजा मौसम बता सकता हूँ। बाकी सवालों के लिए इंटरनेट से जुड़ें।" else "I can show saved weather for today or tomorrow. Reconnect for other questions.")) to day
        val zone=ZoneId.of(b.location.timezone)
        val date=LocalDate.now(zone).plusDays(day.toLong())
        val rows=b.hourly.filter {
            val t=Instant.parse(it.time).atZone(zone)
            t.toLocalDate()==date && when {
                q.contains("morning") || q.contains("सुबह") -> t.hour in 6..11
                q.contains("afternoon") -> t.hour in 12..16
                q.contains("evening") || q.contains("शाम") -> t.hour in 17..21
                else -> true
            }
        }
        if(rows.isEmpty()) return (intro+(if(hi) "उस समय का मौसम सहेजा नहीं गया है। नई जानकारी के लिए इंटरनेट से जुड़ें।" else "There is no saved weather for that time. Reconnect to refresh.")) to day
        val temps=rows.mapNotNull{it.temperature}; val rain=rows.mapNotNull{it.rain_chance}
        val facts=buildList {
            add("${b.location.name} · $date")
            if(temps.isNotEmpty()) add(if(hi) "तापमान: ${temps.min()} से ${temps.max()}°C।" else "Temperature: ${temps.min()} to ${temps.max()}°C.")
            if(rain.isNotEmpty()) add(if(hi) "बारिश की सबसे अधिक संभावना: ${rain.max()}%।" else "Highest hourly chance of rain: ${rain.max()}%.")
            add(if(hi) "बाहर जाने से पहले आधिकारिक चेतावनी देखें।" else "Check official warnings before going out.")
        }
        return (intro+facts.joinToString("\n\n")) to day
    }
}


fun cachedAlertIsActive(alert:OfficialAlert,now:java.time.Instant=java.time.Instant.now()):Boolean {
    val effective=alert.effective?.let { runCatching { java.time.Instant.parse(it) }.getOrNull() }
    val expires=alert.expires?.let { runCatching { java.time.Instant.parse(it) }.getOrNull() }?:return false
    return (effective==null || !effective.isAfter(now)) && expires.isAfter(now)
}

enum class AlertLevel { YELLOW, ORANGE, RED }
fun alertLevel(severity:String):AlertLevel=when(severity.lowercase()) {
    "extreme","severe" -> AlertLevel.RED
    "moderate" -> AlertLevel.ORANGE
    else -> AlertLevel.YELLOW
}
