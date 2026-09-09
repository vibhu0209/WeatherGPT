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
    private val weatherWords=listOf(
        "weather","rain","temperature","wind","today","tomorrow","morning","evening","afternoon",
        "मौसम","बारिश","कल","आज","सुबह","शाम","மாலை","நாளை","மழை","ভোর","কাল","বৃষ্টি","వర్షం","రేపు"
    )

    fun answer(text:String,b:BundleDto?,offset:Int,language:String="en"):Pair<String,Int> {
        val q=text.lowercase()
        val lang=normalize(language)
        val day=when {
            listOf("tomorrow","kal","कल","நாளை","কাল","రేపు","नाही","उद्या").any { q.contains(it) } -> 1
            listOf("today","आज","இன்று","আজ","ఈరోజు","आज").any { q.contains(it) } -> 0
            else -> offset
        }
        if(b==null) return copy(lang,
            en="No saved forecast yet. Connect to the internet and download your weather first.",
            hi="अभी मौसम सहेजा नहीं गया है। इंटरनेट से जुड़कर पहले मौसम डाउनलोड करें.",
        ) to day
        val downloaded=Instant.parse(b.retrieved_at).atZone(ZoneId.of(b.location.timezone))
            .format(java.time.format.DateTimeFormatter.ofPattern("d MMM, h:mm a",java.util.Locale.forLanguageTag(lang)))
        val intro=copy(lang,
            en="Saved forecast from $downloaded. Conditions may have changed.\n\n",
            hi="सहेजा मौसम: $downloaded। जानकारी बदल सकती है।\n\n",
            bn="সংরক্ষিত পূর্বাভাস: $downloaded। অবস্থা বদলাতে পারে।\n\n",
            te="సేవ్ చేసిన అంచనా: $downloaded. పరిస్థితులు మారవచ్చు.\n\n",
            ta="சேமித்த முன்னறிவு: $downloaded. நிலை மாறக்கூடும்.\n\n",
            mr="जतन अंदाज: $downloaded. परिस्थिती बदलू शकते.\n\n",
        )
        if(listOf("warning","alert","चेतावनी","সতর্ক","எச்சரிக்கை","హెచ్చరిక").any{q.contains(it)}) {
            val active=b.official_alerts.orEmpty().filter { alert->cachedAlertIsActive(alert) }
            if(active.isNotEmpty()) {
                val warnings=active.joinToString("\n\n") { alert->
                    val instruction=alert.instruction?:alert.description?:""
                    copy(lang,
                        en="Previously downloaded official warning: ${alert.headline}. $instruction Expires: ${alert.expires}.",
                        hi="पहले डाउनलोड की गई आधिकारिक चेतावनी: ${alert.headline}। $instruction समाप्ति: ${alert.expires}.",
                    )
                }
                val needNet=copy(lang,
                    en="New warnings and updates require an internet connection.",
                    hi="नई चेतावनियों और बदलावों के लिए इंटरनेट चाहिए।",
                )
                return (intro+warnings+"\n\n"+needNet) to day
            }
            val status=(b.official_status?:b.alerts_status).lowercase()
            val statusMsg=when(status) {
                "available" -> copy(lang,
                    en="Saved feed reported no active official warning here. New warnings need an internet connection. Refresh before going out.",
                    hi="सहेजी सेवा में यहाँ कोई सक्रिय आधिकारिक चेतावनी नहीं थी। नई चेतावनियों के लिए इंटरनेट चाहिए। बाहर जाने से पहले फिर जाँचें।",
                )
                else -> copy(lang,
                    en="New warnings need an internet connection. Official warning availability is unknown. Check IMD before going out.",
                    hi="नई चेतावनियों के लिए इंटरनेट चाहिए। आधिकारिक चेतावनी उपलब्धता पता नहीं है। बाहर जाने से पहले IMD की चेतावनी देखें।",
                )
            }
            return (intro+statusMsg) to day
        }
        if(listOf("climate","years","monsoon","जलवायु","سال").any{q.contains(it)}) {
            return (intro+copy(lang,
                en="Historical climate analysis needs an internet connection for ERA5 data. Reconnect to ask about long-term trends.",
                hi="ऐतिहासिक जलवायु विश्लेषण के लिए ERA5 डेटा हेतु इंटरनेट चाहिए। लंबे रुझान के लिए फिर जुड़ें।",
            )) to day
        }
        if(!weatherWords.any{q.contains(it)}) return (intro+copy(lang,
            en="I can show saved weather for today or tomorrow. Reconnect for other questions.",
            hi="मैं आज या कल का सहेजा मौसम बता सकता हूँ। बाकी सवालों के लिए इंटरनेट से जुड़ें।",
        )) to day
        val zone=ZoneId.of(b.location.timezone)
        val date=LocalDate.now(zone).plusDays(day.toLong())
        val rows=b.hourly.filter {
            val t=Instant.parse(it.time).atZone(zone)
            t.toLocalDate()==date && when {
                q.contains("morning") || q.contains("सुबह") || q.contains("காலை") -> t.hour in 6..11
                q.contains("afternoon") || q.contains("दोपहर") -> t.hour in 12..16
                q.contains("evening") || q.contains("शाम") || q.contains("மாலை") -> t.hour in 17..21
                else -> true
            }
        }
        if(rows.isEmpty()) return (intro+copy(lang,
            en="There is no saved weather for that time. Reconnect to refresh.",
            hi="उस समय का मौसम सहेजा नहीं गया है। नई जानकारी के लिए इंटरनेट से जुड़ें।",
        )) to day
        val temps=rows.mapNotNull{it.temperature}; val rain=rows.mapNotNull{it.rain_chance}
        val facts=buildList {
            add("${b.location.name} · $date")
            if(temps.isNotEmpty()) add(copy(lang,
                en="Temperature: ${temps.min()} to ${temps.max()}°C.",
                hi="तापमान: ${temps.min()} से ${temps.max()}°C।",
                bn="তাপমাত্রা: ${temps.min()} থেকে ${temps.max()}°C।",
                te="ఉష్ణోగ్రత: ${temps.min()} నుండి ${temps.max()}°C.",
                ta="வெப்பநிலை: ${temps.min()} முதல் ${temps.max()}°C.",
                mr="तापमान: ${temps.min()} ते ${temps.max()}°C.",
            ))
            if(rain.isNotEmpty()) add(copy(lang,
                en="Highest hourly chance of rain: ${rain.max()}%.",
                hi="बारिश की सबसे अधिक संभावना: ${rain.max()}%.",
                bn="বৃষ্টির সর্বোচ্চ সম্ভাবনা: ${rain.max()}%.",
                te="అత్యధిక వర్ష అవకాశం: ${rain.max()}%.",
                ta="அதிகபட்ச மழை வாய்ப்பு: ${rain.max()}%.",
                mr="पावसाची सर्वाधिक शक्यता: ${rain.max()}%.",
            ))
            add(copy(lang,
                en="Check official warnings before going out.",
                hi="बाहर जाने से पहले आधिकारिक चेतावनी देखें।",
            ))
        }
        return (intro+facts.joinToString("\n\n")) to day
    }

    private fun normalize(language:String)=when(language.lowercase()) {
        "hi","bn","te","mr","ta","gu","kn","ml","pa","or","en" -> language.lowercase()
        else -> "en"
    }

    private fun copy(lang:String,en:String,hi:String=en,bn:String=en,te:String=en,ta:String=en,mr:String=en,gu:String=en,kn:String=en,ml:String=en,pa:String=en,or:String=en)=when(lang) {
        "hi" -> hi; "bn" -> bn; "te" -> te; "ta" -> ta; "mr" -> mr; "gu" -> gu; "kn" -> kn; "ml" -> ml; "pa" -> pa; "or" -> or; else -> en
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

fun purposeToProfile(purpose:String)=when(purpose.lowercase()) {
    "farm","farming" -> "farming"
    "harbour","fishing","harbor" -> "fishing"
    "work","construction","outdoor" -> "outdoor"
    else -> "general"
}
