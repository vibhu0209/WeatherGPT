package `in`.weathergpt

import android.app.Activity
import android.content.Intent
import android.content.Context
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.os.Bundle
import android.speech.RecognizerIntent
import android.speech.tts.TextToSpeech
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.activity.compose.setContent
import androidx.compose.foundation.*
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.core.tween
import androidx.compose.ui.layout.ContentScale
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.*
import androidx.lifecycle.viewmodel.compose.viewModel
import java.time.*
import java.time.format.DateTimeFormatter
import java.util.Locale

class MainActivity:ComponentActivity() {
    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { WeatherApp(initialTab=intent.getIntExtra("open_tab",0)) }
    }
}
private val LocalTranslatedContext=staticCompositionLocalOf<Context>{error("Translated context is unavailable")}
private val profileOptions=listOf("general" to R.string.general,"farming" to R.string.farming,"fishing" to R.string.fishing,"outdoor" to R.string.outdoor,"tourism" to R.string.tourism,"transport" to R.string.transport,"construction" to R.string.construction,"emergency" to R.string.emergency,"vendor" to R.string.vendor,"aviation" to R.string.aviation,"research" to R.string.research)
@Composable fun s(id:Int)=LocalTranslatedContext.current.resources.getString(id)

@Composable fun WeatherApp(vm:WeatherViewModel=viewModel(),initialTab:Int=0) {
    val prefs by vm.preferences.collectAsState()
    val lang=prefs[androidx.datastore.preferences.core.stringPreferencesKey("language")]?:"en"
    val theme=prefs[androidx.datastore.preferences.core.stringPreferencesKey("theme")]?:"system"
    val large=prefs[androidx.datastore.preferences.core.stringPreferencesKey("large")] == "true"
    val original=LocalContext.current
    val currentConfiguration=LocalConfiguration.current
    SideEffect {
        androidx.appcompat.app.AppCompatDelegate.setApplicationLocales(
            androidx.core.os.LocaleListCompat.forLanguageTags(lang)
        )
    }
    val config=Configuration(currentConfiguration).apply {
        val locale=Locale.forLanguageTag(lang)
        setLocale(locale)
        if(android.os.Build.VERSION.SDK_INT>=24) setLocales(android.os.LocaleList(locale))
    }
    val translated=remember(lang,currentConfiguration){original.createConfigurationContext(config)}
    val density=LocalDensity.current
    val dark=theme=="dark" || theme=="system" && isSystemInDarkTheme()
    SideEffect {
        (original as? Activity)?.window?.let { window ->
            androidx.core.view.WindowCompat.getInsetsController(window,window.decorView).apply {
                isAppearanceLightStatusBars=!dark
                isAppearanceLightNavigationBars=!dark
            }
        }
    }
    CompositionLocalProvider(LocalTranslatedContext provides translated, LocalDensity provides Density(density.density,density.fontScale*(if(large)1.2f else 1f))) {
        WeatherTheme(darkTheme=dark) {
            Surface(Modifier.fillMaxSize(),color=MaterialTheme.colorScheme.background) { AppContent(vm,initialTab) }
        }
    }
}

@Composable fun AppContent(vm:WeatherViewModel,initialTab:Int=0) {
    var tab by rememberSaveable { mutableStateOf(initialTab) }
    val activity=androidx.activity.compose.LocalActivity.current as? ComponentActivity
    DisposableEffect(activity) {
        val listener=androidx.core.util.Consumer<Intent> { incoming ->
            if(incoming.hasExtra("open_tab")) tab=incoming.getIntExtra("open_tab",tab)
        }
        activity?.addOnNewIntentListener(listener)
        onDispose { activity?.removeOnNewIntentListener(listener) }
    }
    var showPlace by rememberSaveable { mutableStateOf(false) }
    val p by vm.place.collectAsState()
    val b by vm.weather.collectAsState()
    val busy by vm.busy.collectAsState()
    val error by vm.error.collectAsState()
    val chatStatus by vm.chatStatus.collectAsState()
    val failure by vm.failure.collectAsState()
    val context=LocalContext.current
    val prefs by vm.preferences.collectAsState()
    val onboarded=prefs[androidx.datastore.preferences.core.stringPreferencesKey("onboarded")]=="true"
    if(!onboarded) {
        OnboardingScreen(vm,onFinished={ place,purpose ->
            if(place!=null) vm.choose(place,purpose) else {
                vm.save("onboarded","true")
                showPlace=true
            }
        })
        return
    }
    var tts by remember { mutableStateOf<TextToSpeech?>(null) }
    var ttsReady by remember { mutableStateOf(false) }
    val noVoice=s(R.string.voice_unavailable)
    DisposableEffect(Unit) {
        val engine=TextToSpeech(context.applicationContext){status->ttsReady=status==TextToSpeech.SUCCESS}
        tts=engine
        onDispose{engine.stop();engine.shutdown()}
    }
    fun speak(text:String,language:String) {
        val engine=tts
        if(!ttsReady || engine==null || engine.setLanguage(Locale.forLanguageTag(speechLocaleTag(language)))<0) {
            Toast.makeText(context,noVoice,Toast.LENGTH_LONG).show();return
        }
        engine.speak(text,TextToSpeech.QUEUE_FLUSH,null,"answer")
    }
    val loadingLabel=s(R.string.loading)
    val prefsLoaded=prefs.asMap().isNotEmpty()
    LaunchedEffect(p, prefsLoaded) {
        if(!prefsLoaded) return@LaunchedEffect
        if(p!=null) vm.refresh()
        else {
            vm.checkBackend()
            if(shouldPromptForPlace(true,prefs[androidx.datastore.preferences.core.stringPreferencesKey("place")])) showPlace=true
        }
    }
    val fontScale=LocalDensity.current.fontScale
    val choosePlaceLabel=s(R.string.choose_place)
    val placeAnnouncement=p?.name?.let { "$choosePlaceLabel, $it" } ?: choosePlaceLabel
    if(showPlace) PlaceDialog(vm,onDismiss={if(p!=null) showPlace=false},onChoose={ place,purpose -> vm.choose(place,purpose);showPlace=false},autoLocate=false)
    Scaffold(
        containerColor=MaterialTheme.colorScheme.background,
        bottomBar={
            NavigationBar(
                containerColor=MaterialTheme.colorScheme.surface,
                tonalElevation=0.dp,
                modifier=Modifier.wrapContentHeight().heightIn(min=(80f*fontScale.coerceIn(1f,2f)).dp),
            ) {
                listOf(
                    R.string.chat to Icons.Default.ChatBubbleOutline,
                    R.string.home to Icons.Default.Home,
                    R.string.forecast to Icons.Default.WbSunny,
                    R.string.alerts to Icons.Default.NotificationsNone,
                    R.string.settings to Icons.Default.Settings,
                ).forEachIndexed { index,(label,icon)->
                    NavigationBarItem(
                        selected=tab==index,
                        onClick={tab=index},
                        icon={Icon(icon,null)},
                        label={Text(s(label),style=MaterialTheme.typography.labelMedium,maxLines=3,textAlign=TextAlign.Center)},
                        colors=NavigationBarItemDefaults.colors(
                            selectedIconColor=MaterialTheme.colorScheme.onPrimaryContainer,
                            selectedTextColor=MaterialTheme.colorScheme.onPrimaryContainer,
                            indicatorColor=MaterialTheme.colorScheme.primaryContainer,
                        ),
                    )
                }
            }
        },
        topBar={
            Surface(color=MaterialTheme.colorScheme.surface,shadowElevation=0.dp) {
                Column(Modifier.statusBarsPadding().padding(horizontal=Space.screen,vertical=Space.md),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                    Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(Space.sm)) {
                        Image(
                            painter=painterResource(R.drawable.weather_gpt_logo),
                            contentDescription="WeatherGPT",
                            contentScale=ContentScale.Fit,
                            modifier=Modifier
                                .size(40.dp)
                                .padding(2.dp),
                        )
                        Text("WeatherGPT",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.SemiBold,color=MaterialTheme.colorScheme.primary,maxLines=1)
                    }
                    Surface(
                        onClick={showPlace=true},
                        color=MaterialTheme.colorScheme.surfaceVariant.copy(alpha=0.55f),
                        shape=MaterialTheme.shapes.small,
                        modifier=Modifier.fillMaxWidth().heightIn(min=Space.touch).semantics { contentDescription=placeAnnouncement; role=Role.Button },
                    ) {
                        Row(Modifier.padding(horizontal=Space.md),verticalAlignment=Alignment.CenterVertically) {
                            Icon(Icons.Default.LocationOn,null,tint=MaterialTheme.colorScheme.primary,modifier=Modifier.size(22.dp))
                            Spacer(Modifier.width(Space.sm))
                            Text(p?.name?:choosePlaceLabel,style=MaterialTheme.typography.titleMedium,modifier=Modifier.weight(1f))
                            Icon(Icons.Default.ExpandMore,null,tint=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        },
    ) { padding ->
        Column(Modifier.padding(padding).imePadding().fillMaxSize()) {
            // One banner from weatherFailure + current Room weather only.
            // Chat offline bubbles must not sticky-drive this notice.
            val notice=noticeFor(failure,b!=null,b?.is_stale==true)
            val cacheAge=b?.let { "${s(R.string.updated)} ${ageMinutes(it.retrieved_at)} ${s(R.string.minutes_ago)}" }
            fun cachedNotice(message:String)=listOfNotNull(message,cacheAge).joinToString(" ")
            androidx.compose.runtime.LaunchedEffect(notice,failure,b!=null,b?.is_stale==true,busy) {
                logNoticeState(notice,failure,b!=null,b?.is_stale==true,offline=vm.offline.value,backendOnline=vm.backendOnline.value,refreshing=busy)
            }
            when(notice) {
                WeatherNotice.NONE->{}
                WeatherNotice.STALE->StatusBanner(cachedNotice(s(R.string.saved_notice)), BannerTone.QUIET)
                WeatherNotice.OFFLINE_CACHED->StatusBanner(cachedNotice(s(R.string.notice_offline_cached)), BannerTone.QUIET)
                WeatherNotice.CANT_CONNECT->StatusBanner(cachedNotice(s(R.string.notice_cant_connect)), BannerTone.QUIET)
                WeatherNotice.PROVIDER_DOWN->StatusBanner(cachedNotice(s(R.string.notice_provider_down)), BannerTone.WARN)
                WeatherNotice.NO_DATA->StatusBanner(s(R.string.notice_no_data), BannerTone.WARN)
                WeatherNotice.NO_SAVED->StatusBanner(s(R.string.notice_no_saved), BannerTone.INFO)
                WeatherNotice.PROVIDERS_UNAVAILABLE->StatusBanner(s(R.string.notice_providers_unavailable), BannerTone.WARN)
                WeatherNotice.CHECK_SETTINGS->StatusBanner(s(R.string.notice_check_settings), BannerTone.WARN)
            }
            if(error=="no_places"||error=="search_failed"||error=="location_failed")
                StatusBanner(s(when(error){"no_places"->R.string.no_places;"search_failed"->R.string.search_failed;else->R.string.location_unavailable}))
            if(busy) LinearProgressIndicator(Modifier.fillMaxWidth().semantics{contentDescription=loadingLabel})
            when(tab) {
                0 -> ChatScreen(vm,p,b,busy,chatStatus,{showPlace=true},::speak)
                1 -> HomeScreen(vm,b,busy,{vm.refresh()},{showPlace=true},onAsk={tab=0},onRetryConnection={vm.checkBackend()})
                2 -> ForecastScreen(b,busy,failure,{vm.refresh()},{showPlace=true})
                3 -> AlertScreen(vm,b,::speak)
                else -> SettingsScreen(vm,onOpenChat={tab=0})
            }
        }
    }
}

@Composable fun HomeScreen(vm:WeatherViewModel,b:BundleDto?,busy:Boolean,refresh:()->Unit,choose:()->Unit,onAsk:()->Unit,onRetryConnection:()->Unit) {
    val profile=vm.value("profile","general")
    val score=b?.scores?.get(profile)
    val tip=primaryAdviceMessage(b?.recommendations?.get(profile))
    val failure by vm.failure.collectAsState()
    var alertOpen by rememberSaveable { mutableStateOf(false) }
    val locale=Locale.getDefault()
    val refreshLabel=s(R.string.refresh_weather)
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(horizontal=Space.screen,vertical=Space.md),verticalArrangement=Arrangement.spacedBy(Space.md)) {
        if(b==null) {
            if(failure==NetFailure.NONE) item { Text(s(R.string.no_saved),style=MaterialTheme.typography.bodyLarge) }
            item { PrimaryWeatherButton(s(R.string.search),Icons.Default.Search,choose) }
            item { QuietButton(s(R.string.retry_connection),Icons.Default.Refresh,onRetryConnection) }
        } else {
            val activeOfficial=b.official_alerts.orEmpty().filter { cachedAlertIsActive(it) && Freshness.officialAlert(b.retrieved_at,it.expires)!=FreshnessState.STALE }
            if(activeOfficial.isNotEmpty()) {
                item {
                    Column(verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                        Text(s(R.string.home_alerts),style=MaterialTheme.typography.titleMedium)
                        AlertSummary(activeOfficial.first(),alertOpen,{alertOpen=!alertOpen})
                    }
                }
            } else {
                val status=(b.official_status?:b.alerts_status?:"").lowercase()
                if(status!="available") {
                    item {
                        Text(s(R.string.alert_unknown),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            item {
                val hour=nearestHour(b)
                val code=hour?.weather_code?.toInt()
                val condition=conditionResource(code)?.let { s(it) }
                val atmosphere=weatherAtmosphere(code)
                val feelsLikeLabel=s(R.string.feels_like)
                val upcoming=b.hourly.filter{Instant.parse(it.time)>Instant.now().minusSeconds(3600)}.take(12)
                Surface(
                    color=if(atmosphere.alpha>0f) atmosphere else MaterialTheme.colorScheme.surface,
                    shape=MaterialTheme.shapes.large,
                    modifier=Modifier.fillMaxWidth(),
                ) {
                    Column(
                        Modifier.padding(horizontal=Space.lg,vertical=Space.lg).semantics(mergeDescendants=true) {
                            contentDescription=listOfNotNull(
                                b.location.name,
                                hour?.temperature?.let { "${it}°C" },
                                condition,
                                hour?.apparent_temperature?.let { "$feelsLikeLabel ${it}°C" },
                            ).joinToString(", ")
                        },
                        verticalArrangement=Arrangement.spacedBy(Space.md),
                    ) {
                        Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(Space.sm)) {
                            Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(2.dp)) {
                                Text(b.location.name,style=MaterialTheme.typography.titleMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                                Text("${s(R.string.updated)} ${ageMinutes(b.retrieved_at)} ${s(R.string.minutes_ago)}",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            if(busy) CircularProgressIndicator(Modifier.size(18.dp),strokeWidth=2.dp)
                            else IconButton(
                                onClick=refresh,
                                modifier=Modifier.size(40.dp).semantics{contentDescription=refreshLabel},
                            ) { Icon(Icons.Default.Refresh,null,modifier=Modifier.size(20.dp),tint=MaterialTheme.colorScheme.onSurfaceVariant) }
                        }
                        Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(Space.lg)) {
                            ConditionIcon(code, condition, size=56.dp)
                            Column(verticalArrangement=Arrangement.spacedBy(Space.xs)) {
                                if(hour?.temperature!=null) Text("${hour.temperature.toInt()}°",style=MaterialTheme.typography.displayLarge,fontWeight=FontWeight.Bold)
                                condition?.let { Text(it,style=MaterialTheme.typography.titleLarge) }
                                if(hour?.apparent_temperature!=null) Text("$feelsLikeLabel ${hour.apparent_temperature.toInt()}°",style=MaterialTheme.typography.bodyLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        MetricRow(
                            listOf(
                                s(R.string.rain) to (hour?.rain_chance?.let{"${it.toInt()}%"}?:s(R.string.unavailable)),
                                s(R.string.wind) to (formatWindKmh(hour?.wind_ms,locale)?.let{"$it ${s(R.string.unit_kmh)}"}?:s(R.string.unavailable)),
                                s(R.string.humidity) to (hour?.humidity?.let{"${it.toInt()}%"}?:s(R.string.unavailable)),
                            ),
                            stack=LocalDensity.current.fontScale>=1.5f,
                        )
                        if(upcoming.isNotEmpty()) {
                            val rainLabel=s(R.string.rain)
                            val unavailable=s(R.string.unavailable)
                            LazyRow(horizontalArrangement=Arrangement.spacedBy(Space.sm)) {
                                items(upcoming, key={it.time}) { h ->
                                    val timeLabel=Instant.parse(h.time).atZone(ZoneId.of(b.location.timezone)).format(DateTimeFormatter.ofPattern("h a"))
                                    val temp=h.temperature?.let{"${it.toInt()}°C"}?:unavailable
                                    val rain=h.rain_chance?.let{"${it.toInt()}%"}?:"—"
                                    val hCode=h.weather_code?.toInt()
                                    Surface(
                                        color=MaterialTheme.colorScheme.surface.copy(alpha=0.85f),
                                        shape=MaterialTheme.shapes.small,
                                        modifier=Modifier.width(68.dp).semantics(mergeDescendants=true) {
                                            contentDescription=hourlyTalkBack(timeLabel,temp,rainLabel,rain)
                                        },
                                    ) {
                                        Column(
                                            Modifier.padding(vertical=Space.sm,horizontal=Space.xs),
                                            horizontalAlignment=Alignment.CenterHorizontally,
                                            verticalArrangement=Arrangement.spacedBy(Space.xs),
                                        ) {
                                            Text(timeLabel,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                                            ConditionIcon(hCode, null, size=20.dp)
                                            Text(h.temperature?.let{"${it.toInt()}°"}?:unavailable,style=MaterialTheme.typography.titleSmall,fontWeight=FontWeight.SemiBold)
                                            Text(h.rain_chance?.let{"${it.toInt()}%"}?:"—",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                                        }
                                    }
                                }
                            }
                        }
                        if(score!=null) WeatherScoreCard(score)
                        ConfidenceNote(b, score)
                        tip?.let { Text(it,style=MaterialTheme.typography.bodyLarge) }
                    }
                }
            }
            if(b.risk_estimates.orEmpty().isNotEmpty()) {
                item {
                    Column(verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                        b.risk_estimates.orEmpty().firstOrNull()?.let { risk ->
                            Surface(color=MaterialTheme.colorScheme.surfaceVariant.copy(alpha=0.5f),shape=MaterialTheme.shapes.small) {
                                Column(Modifier.padding(Space.lg),verticalArrangement=Arrangement.spacedBy(Space.xs)) {
                                    Text(s(R.string.weather_risk),style=MaterialTheme.typography.labelLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                                    Text(risk.message,style=MaterialTheme.typography.bodyLarge)
                                }
                            }
                        }
                    }
                }
            }
            item { PrimaryWeatherButton(s(R.string.ask_weathergpt),Icons.Default.ChatBubbleOutline,onAsk) }
        }
    }
}
@Composable fun BigButton(label:String,icon:androidx.compose.ui.graphics.vector.ImageVector,onClick:()->Unit,enabled:Boolean=true) {
    PrimaryWeatherButton(label,icon,onClick,enabled)
}
fun conditionResource(code:Int?):Int?=when(code) { 0->R.string.clear_sky;1,2,3->R.string.cloudy;45,48->R.string.fog;51,53,55,56,57->R.string.drizzle;61,63,65,66,67->R.string.rainy;71,73,75,77->R.string.snow;80,81,82,85,86->R.string.showers;95,96,99->R.string.thunderstorm;else->null }

/** Emphasize a recommended time window when the answer leads with one — visual only, no invented weather. */
fun recommendationEmphasis(body:String):Pair<String,String>? {
    val window=Regex("""(?i)(\d{1,2}\s*(?:[–\-]|to)\s*\d{1,2}\s*(?:AM|PM|a\.m\.|p\.m\.)?)""")
    val paragraphs=body.trim().split(Regex("""\n\s*\n"""), limit=2)
    val lead=paragraphs.firstOrNull()?.trim().orEmpty()
    if(lead.isEmpty() || !window.containsMatchIn(lead)) return null
    if(lead.length>160) return null
    val rest=paragraphs.getOrNull(1)?.trim().orEmpty().ifEmpty {
        body.removePrefix(lead).trimStart('\n',' ')
    }
    return lead to rest
}

@Composable
fun compactFollowUpLabel(raw:String):String {
    val lower=raw.lowercase()
    return when {
        "why" in lower && ("window" in lower || "time" in lower || "recommend" in lower) -> s(R.string.chip_why_time)
        "hourly" in lower || "hour by" in lower || "next three" in lower -> s(R.string.chip_hourly)
        "warning" in lower || "alert" in lower -> s(R.string.chip_warnings)
        "rain" in lower -> s(R.string.chip_rain_later)
        "tomorrow" in lower -> s(R.string.chip_tomorrow)
        "score" in lower -> s(R.string.chip_score)
        "wave" in lower || "swell" in lower || "wind" in lower -> s(R.string.chip_wind_waves)
        "marine" in lower || "sea" in lower -> s(R.string.chip_sea)
        "outdoor" in lower || "outside" in lower || "field" in lower || "work time" in lower || "spray" in lower -> s(R.string.chip_best_work)
        raw.length <= 18 -> raw
        else -> raw.take(16).trimEnd() + "…"
    }
}

@Composable fun ChatScreen(vm:WeatherViewModel,p:Place?,b:BundleDto?,busy:Boolean,chatStatus:String,choose:()->Unit,speak:(String,String)->Unit) {
    val messages by vm.messages.collectAsState()
    val compare by vm.comparePlace.collectAsState()
    val saved by vm.savedPlaces.collectAsState()
    val offline by vm.offline.collectAsState()
    var draft by rememberSaveable { mutableStateOf("") }
    val context=LocalContext.current
    val unavailable=s(R.string.voice_unavailable)
    val profile=vm.value("profile","general")
    val starters=when(profile) {
        "farming" -> listOf(
            R.string.chip_best_work to R.string.farm_work_question,
            R.string.chip_rain_later to R.string.chip_rain_later,
            R.string.chip_warnings to R.string.warning_question,
        )
        "fishing" -> listOf(
            R.string.chip_sea to R.string.marine_question,
            R.string.chip_wind_waves to R.string.wave_question,
            R.string.chip_warnings to R.string.warning_question,
        )
        "tourism","outdoor" -> listOf(
            R.string.chip_best_outdoor to R.string.chip_best_outdoor,
            R.string.chip_rain_later to R.string.chip_rain_later,
            R.string.chip_tomorrow to R.string.tomorrow_question,
        )
        else -> listOf(
            R.string.chip_will_rain to R.string.rain_question,
            R.string.chip_best_outdoor to R.string.chip_best_outdoor,
            R.string.chip_tomorrow to R.string.tomorrow_question,
        )
    }
    val dynamicFollowUps by vm.followUps.collectAsState()
    val messageListState=rememberLazyListState()
    LaunchedEffect(messages.lastOrNull()?.id) {
        if(messages.isNotEmpty()) messageListState.animateScrollToItem(0)
    }
    val typeQuestion=s(R.string.type_question)
    val speakLabel=s(R.string.speak)
    val sendLabel=s(R.string.send)
    val launcher=rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result->
        if(result.resultCode==Activity.RESULT_OK) draft=result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()?.take(1000)?:draft
    }
    val comparePrefix=s(R.string.compare_prefix)
    fun sendChat(raw:String) {
        val text=raw.trim()
        if(text.isBlank()) return
        val withCompare=if(compare!=null && !listOf("compare","तुलना"," vs ").any{text.lowercase().contains(it)}) {
            String.format(comparePrefix, compare!!.name) + text
        } else text
        vm.send(withCompare)
    }
    val downloaded=s(R.string.downloaded_prefix)
    val hour=b?.let { nearestHour(it) }
    val code=hour?.weather_code?.toInt()
    val condition=conditionResource(code)?.let { s(it) }
    val score=b?.scores?.get(profile)?.score
    val tip=primaryAdviceMessage(b?.recommendations?.get(profile))
    val placeShort=p?.name?.substringBefore(",")?.trim().orEmpty()
    val greeting=when(LocalTime.now().hour) {
        in 5..11 -> s(R.string.good_morning)
        in 12..16 -> s(R.string.good_afternoon)
        else -> s(R.string.good_evening)
    }
    Column(Modifier.fillMaxSize()) {
        if(p!=null && b!=null) {
            WeatherContextStrip(
                placeName=p.name,
                temperature=hour?.temperature,
                weatherCode=code,
                conditionLabel=condition,
                score=score,
                adviceLine=if(messages.isEmpty()) tip else null,
                modifier=Modifier.padding(horizontal=Space.screen,vertical=Space.sm),
            )
            ConfidenceNote(b, b.scores?.get(profile), Modifier.padding(horizontal=Space.screen))
        }
        if(chatStatus.isNotEmpty()) {
            StatusBanner(
                s(if(chatStatus=="sending") R.string.sending_question else R.string.checking_sources),
                BannerTone.QUIET,
            )
        }
        LazyColumn(Modifier.weight(1f).fillMaxWidth(),state=messageListState,contentPadding=PaddingValues(Space.screen),verticalArrangement=Arrangement.spacedBy(Space.md),reverseLayout=true) {
            items(messages.reversed(),key={it.id}) { m ->
                val user=m.role=="user"
                val split=if(!user) m.text.split("\n\n$downloaded") else listOf(m.text)
                val rawBody=split.first()
                val body=if(user) rawBody else stripUncertaintyBoilerplate(rawBody)
                val meta=if(split.size>1) downloaded+split.drop(1).joinToString("\n\n$downloaded") else null
                var open by rememberSaveable(m.id) { mutableStateOf(false) }
                Appear {
                    Row(Modifier.fillMaxWidth().wrapContentHeight(unbounded=true),horizontalArrangement=if(user) Arrangement.End else Arrangement.Start) {
                        if(user) {
                            Surface(
                                color=MaterialTheme.colorScheme.primaryContainer,
                                contentColor=MaterialTheme.colorScheme.onPrimaryContainer,
                                shape=MaterialTheme.shapes.medium,
                                modifier=Modifier.widthIn(max=340.dp).fillMaxWidth(0.82f),
                            ) {
                                Text(body,Modifier.padding(horizontal=Space.lg,vertical=Space.md),style=MaterialTheme.typography.bodyLarge)
                            }
                        } else {
                            val emphasis=recommendationEmphasis(body)
                            Column(Modifier.fillMaxWidth(0.96f),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                                Text("WeatherGPT",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.primary)
                                if(emphasis!=null) {
                                    Surface(
                                        color=MaterialTheme.colorScheme.primaryContainer.copy(alpha=0.4f),
                                        shape=MaterialTheme.shapes.medium,
                                        modifier=Modifier.fillMaxWidth().animateContentSize(),
                                    ) {
                                        Text(emphasis.first,Modifier.padding(Space.lg),style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.SemiBold)
                                    }
                                    if(emphasis.second.isNotBlank()) {
                                        Text(emphasis.second.trim(),style=MaterialTheme.typography.bodyLarge)
                                    }
                                } else {
                                    Text(body,style=MaterialTheme.typography.bodyLarge)
                                }
                                FlowRow(verticalArrangement=Arrangement.spacedBy(Space.xs),horizontalArrangement=Arrangement.spacedBy(Space.sm)) {
                                    TextButton(onClick={speak(m.text,m.language)},modifier=Modifier.heightIn(min=Space.touch)) {
                                        Icon(Icons.AutoMirrored.Filled.VolumeUp,null,modifier=Modifier.size(20.dp));Spacer(Modifier.width(Space.sm));Text(s(R.string.listen))
                                    }
                                    if(meta!=null) TextButton(onClick={open=!open},modifier=Modifier.heightIn(min=Space.touch)) {
                                        Text(s(if(open) R.string.hide_details else R.string.show_details))
                                    }
                                }
                                if(open && meta!=null) {
                                    Text(meta,style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                            }
                        }
                    }
                }
            }
            if(messages.isEmpty()) item {
                Column(verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                    Text(greeting,style=MaterialTheme.typography.headlineSmall)
                    when {
                        offline && b!=null && placeShort.isNotEmpty() -> {
                            Text(String.format(s(R.string.place_saved_offline), placeShort),style=MaterialTheme.typography.bodyLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(s(R.string.chat_offline_hint),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        b==null && p!=null -> Text(s(R.string.chat_need_download_hint),style=MaterialTheme.typography.bodyLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        b==null -> Text(s(R.string.chat_no_weather_hint),style=MaterialTheme.typography.bodyLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        hour?.temperature!=null && placeShort.isNotEmpty() -> {
                            Text(String.format(s(R.string.place_now_temp), placeShort, hour.temperature.toInt()),style=MaterialTheme.typography.titleMedium)
                        }
                    }
                    Text(s(R.string.chat_planning_prompt),style=MaterialTheme.typography.titleMedium)
                    if(p==null) PrimaryWeatherButton(s(R.string.search),Icons.Default.Search,choose)
                }
            }
        }
        if(p!=null) Surface(color=MaterialTheme.colorScheme.surface,tonalElevation=1.dp) {
            Column(Modifier.navigationBarsPadding().imePadding().padding(horizontal=Space.screen,vertical=Space.md),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                val others=saved.filter { it.latitude!=p.latitude || it.longitude!=p.longitude }
                if(others.isNotEmpty()) {
                    Text(s(R.string.compare_place),style=MaterialTheme.typography.labelLarge)
                    FlowRow(horizontalArrangement=Arrangement.spacedBy(Space.sm),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                        others.forEach { place ->
                            FilterChip(
                                selected=compare!=null && compare!!.latitude==place.latitude && compare!!.longitude==place.longitude,
                                onClick={ vm.setComparePlace(if(compare!=null && compare!!.latitude==place.latitude) null else place.place()) },
                                label={ Text(String.format(s(R.string.compare_with), place.label)) },
                                modifier=Modifier.heightIn(min=Space.touch),
                            )
                        }
                        if(compare!=null) TextButton(onClick={vm.setComparePlace(null)},modifier=Modifier.heightIn(min=Space.touch)) { Text(s(R.string.clearing_compare)) }
                    }
                }
                if(messages.isEmpty() && LocalDensity.current.fontScale<1.5f) {
                    FlowRow(horizontalArrangement=Arrangement.spacedBy(Space.sm),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                        starters.forEach { (labelId, promptId) ->
                            val prompt=s(promptId)
                            SuggestionChip(s(labelId),!busy){sendChat(prompt)}
                        }
                    }
                } else if(messages.isNotEmpty() && LocalDensity.current.fontScale<1.5f) FlowRow(horizontalArrangement=Arrangement.spacedBy(Space.sm),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                    val followPrompts = if(dynamicFollowUps.isNotEmpty()) dynamicFollowUps else listOf(
                        s(R.string.chip_why_time),
                        s(R.string.chip_hourly),
                        s(R.string.chip_warnings),
                    )
                    followPrompts.take(3).forEach { question ->
                        SuggestionChip(compactFollowUpLabel(question),!busy){sendChat(question)}
                    }
                }
                Row(verticalAlignment=Alignment.Bottom,horizontalArrangement=Arrangement.spacedBy(Space.sm)) {
                    OutlinedTextField(
                        value=draft,
                        onValueChange={draft=it.take(1000)},
                        placeholder={Text(typeQuestion)},
                        modifier=Modifier.weight(1f).heightIn(min=Space.touch),
                        textStyle=MaterialTheme.typography.bodyLarge,
                        maxLines=3,
                        shape=MaterialTheme.shapes.medium,
                        colors=OutlinedTextFieldDefaults.colors(
                            focusedBorderColor=MaterialTheme.colorScheme.primary,
                            unfocusedBorderColor=MaterialTheme.colorScheme.outline.copy(alpha=0.4f),
                        ),
                    )
                    IconButton(onClick={
                        try { launcher.launch(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                            putExtra(RecognizerIntent.EXTRA_LANGUAGE,speechLocaleTag(vm.value("language","en")))
                            putExtra(RecognizerIntent.EXTRA_PROMPT,typeQuestion)
                        }) } catch(e:android.content.ActivityNotFoundException) { Toast.makeText(context,unavailable,Toast.LENGTH_LONG).show() }
                    },enabled=!busy,modifier=Modifier.size(Space.touch).semantics{contentDescription=speakLabel}) { Icon(Icons.Default.Mic,null) }
                    FilledIconButton(onClick={sendChat(draft);draft=""},enabled=draft.isNotBlank()&&!busy,modifier=Modifier.size(Space.touch).semantics{contentDescription=sendLabel}) { Icon(Icons.AutoMirrored.Filled.Send,null) }
                }
            }
        }
    }
}
@Composable fun WeatherCard(b:BundleDto, busy:Boolean=false, onRefresh:(()->Unit)?=null) {
    var details by rememberSaveable(b.retrieved_at) { mutableStateOf(false) }
    val hour=nearestHour(b)
    val locale=Locale.getDefault()
    val code=hour?.weather_code?.toInt()
    val condition=conditionResource(code)?.let { s(it) }
    val atmosphere=weatherAtmosphere(code)
    val refreshLabel=s(R.string.refresh_weather)
    Surface(
        color=if(atmosphere.alpha>0f) atmosphere else MaterialTheme.colorScheme.surface,
        shape=MaterialTheme.shapes.large,
        modifier=Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(Space.xl),verticalArrangement=Arrangement.spacedBy(Space.md)) {
            Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(Space.lg)) {
                ConditionIcon(code, condition, size=48.dp)
                Column(verticalArrangement=Arrangement.spacedBy(Space.xs),modifier=Modifier.weight(1f)) {
                    if(hour?.temperature!=null) Text("${hour.temperature.toInt()}°",style=MaterialTheme.typography.displayMedium)
                    condition?.let { Text(it,style=MaterialTheme.typography.titleMedium) }
                }
            }
            Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(Space.sm)) {
                Text(
                    "${s(R.string.updated)} ${ageMinutes(b.retrieved_at)} ${s(R.string.minutes_ago)}",
                    style=MaterialTheme.typography.labelLarge,
                    color=MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier=Modifier.weight(1f),
                )
                if(onRefresh!=null) {
                    if(busy) CircularProgressIndicator(Modifier.size(18.dp),strokeWidth=2.dp)
                    else IconButton(
                        onClick=onRefresh,
                        modifier=Modifier.size(40.dp).semantics{contentDescription=refreshLabel},
                    ) { Icon(Icons.Default.Refresh,null,modifier=Modifier.size(20.dp),tint=MaterialTheme.colorScheme.onSurfaceVariant) }
                }
            }
            TextButton(onClick={details=!details},modifier=Modifier.heightIn(min=Space.touch)) {
                Text(s(if(details) R.string.hide_details else R.string.show_details))
            }
            if(details) {
                if(hour?.temperature!=null) Text("${s(R.string.temperature)}: ${hour.temperature}°C",style=MaterialTheme.typography.bodyMedium)
                if(hour?.rain_chance!=null) Text("${s(R.string.rain)}: ${hour.rain_chance}%",style=MaterialTheme.typography.bodyMedium)
                if(hour?.wind_ms!=null) Text("${s(R.string.wind)}: ${formatWindKmh(hour.wind_ms,locale)} ${s(R.string.unit_kmh)}",style=MaterialTheme.typography.bodyMedium)
                formatWindKmh(hour?.wind_gust_ms,locale)?.let { Text("${s(R.string.gusts)}: $it ${s(R.string.unit_kmh)}",style=MaterialTheme.typography.bodyMedium) }
                if(hour?.humidity!=null) Text("${s(R.string.humidity)}: ${hour.humidity}%",style=MaterialTheme.typography.bodyMedium)
                hour?.visibility_m?.let { Text("${s(R.string.visibility)}: ${String.format(locale,"%.1f",it/1000.0)} ${s(R.string.unit_km)}",style=MaterialTheme.typography.bodyMedium) }
                hour?.uv_index?.let { Text("${s(R.string.uv)}: $it",style=MaterialTheme.typography.bodyMedium) }
                Text("${s(R.string.sources)}: ${b.sources.joinToString()}",style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                if(b.source_count==1) Text(s(R.string.single_source),style=MaterialTheme.typography.bodyMedium)
                b.confidence?.let { confidence ->
                    Text("${s(R.string.forecast_confidence)}: ${confidence.score}/100 · ${confidence.label}",style=MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}
@Composable fun ForecastScreen(b:BundleDto?,busy:Boolean,failure:NetFailure,refresh:()->Unit,choose:()->Unit) {
    var moreHours by rememberSaveable { mutableStateOf(false) }
    LazyColumn(contentPadding=PaddingValues(horizontal=Space.screen,vertical=Space.lg),verticalArrangement=Arrangement.spacedBy(Space.lg),modifier=Modifier.fillMaxSize()) {
        item { SectionHeader(s(R.string.forecast)) }
        item { Text(s(R.string.forecast_help),style=MaterialTheme.typography.bodyLarge,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        if(b==null) {
            if(noticeFor(failure,false,false)==WeatherNotice.NONE) item { Text(s(R.string.no_saved),style=MaterialTheme.typography.bodyLarge) }
            item { PrimaryWeatherButton(s(R.string.choose_place),Icons.Default.LocationOn,choose) }
            item { QuietButton(s(R.string.download),Icons.Default.Download,refresh,!busy) }
        } else {
            item { WeatherCard(b, busy=busy, onRefresh=refresh) }
            item { ConfidenceNote(b) }
            if(b.daily.orEmpty().isNotEmpty()) {
                items(b.daily.orEmpty()) { day ->
                    val rainLabel=s(R.string.rain)
                    val unavailable=s(R.string.unavailable)
                    val dayLabel=runCatching {
                        LocalDate.parse(day.date).format(DateTimeFormatter.ofPattern("EEE d MMM", Locale.getDefault()))
                    }.getOrDefault(day.date)
                    val range="${day.temperature_min?.let{"${it.toInt()}°"}?:unavailable} / ${day.temperature_max?.let{"${it.toInt()}°"}?:unavailable}"
                    val rain=day.rain_chance_max?.let{"${it.toInt()}%"}?:unavailable
                    Row(
                        Modifier.fillMaxWidth().padding(vertical=Space.md).semantics(mergeDescendants=true) {
                            contentDescription=dailyForecastTalkBack(dayLabel,range,rainLabel,rain)
                        },
                        verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.spacedBy(Space.md),
                    ) {
                        Text(dayLabel,style=MaterialTheme.typography.titleMedium,modifier=Modifier.weight(1.2f))
                        Text(range,style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.SemiBold,modifier=Modifier.weight(1f),textAlign=TextAlign.End)
                        Text(rain,style=MaterialTheme.typography.labelLarge,color=MaterialTheme.colorScheme.onSurfaceVariant,modifier=Modifier.widthIn(min=40.dp),textAlign=TextAlign.End)
                    }
                    HorizontalDivider(color=MaterialTheme.colorScheme.outline.copy(alpha=0.25f))
                }
            }
            item { Text(s(R.string.hourly),style=MaterialTheme.typography.titleMedium) }
            val hours=b.hourly.filter{Instant.parse(it.time)>Instant.now().minusSeconds(3600)}.take(24)
            item {
                val rainLabel=s(R.string.rain)
                val unavailable=s(R.string.unavailable)
                LazyRow(horizontalArrangement=Arrangement.spacedBy(Space.sm),contentPadding=PaddingValues(vertical=Space.sm)) {
                    items(hours, key={it.time}) { h ->
                        val timeLabel=Instant.parse(h.time).atZone(ZoneId.of(b.location.timezone)).format(DateTimeFormatter.ofPattern("h a"))
                        val temp=h.temperature?.let{"${it.toInt()}°C"}?:unavailable
                        val rain=h.rain_chance?.let{"${it.toInt()}%"}?:"—"
                        val code=h.weather_code?.toInt()
                        Surface(
                            color=MaterialTheme.colorScheme.surface,
                            shape=MaterialTheme.shapes.small,
                            modifier=Modifier.width(76.dp).semantics(mergeDescendants=true) {
                                contentDescription=hourlyTalkBack(timeLabel,temp,rainLabel,rain)
                            },
                        ) {
                            Column(
                                Modifier.padding(vertical=Space.md,horizontal=Space.sm),
                                horizontalAlignment=Alignment.CenterHorizontally,
                                verticalArrangement=Arrangement.spacedBy(Space.xs),
                            ) {
                                Text(timeLabel,style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                                ConditionIcon(code, null, size=22.dp)
                                Text(h.temperature?.let{"${it.toInt()}°"}?:unavailable,style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.SemiBold)
                                Text(h.rain_chance?.let{"${it.toInt()}%"}?:"—",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
            item {
                TextButton(onClick={moreHours=!moreHours},modifier=Modifier.heightIn(min=Space.touch)) {
                    Text(s(if(moreHours) R.string.hide_details else R.string.show_details))
                }
            }
            if(moreHours) items(hours.drop(8)) { h ->
                val rainLabel=s(R.string.rain)
                val unavailable=s(R.string.unavailable)
                val timeLabel=Instant.parse(h.time).atZone(ZoneId.of(b.location.timezone)).format(DateTimeFormatter.ofPattern("EEE · h a"))
                val temp=h.temperature?.let{"$it°C"}?:unavailable
                val rain=h.rain_chance?.let{"$it%"}?:unavailable
                Column(
                    Modifier.fillMaxWidth().padding(vertical=Space.xs).semantics(mergeDescendants=true) {
                        contentDescription=hourlyTalkBack(timeLabel,temp,rainLabel,rain)
                    },
                    verticalArrangement=Arrangement.spacedBy(Space.xs),
                ) {
                    Text(timeLabel,style=MaterialTheme.typography.bodyMedium)
                    Text(temp,style=MaterialTheme.typography.bodyMedium)
                    Text(rain,style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            item { Text("${s(R.string.sources)}: ${b.sources.joinToString()}",style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}
@Composable fun AlertScreen(vm:WeatherViewModel,bundle:BundleDto?,speak:(String,String)->Unit={_,_->}) {
    val context=LocalContext.current
    val hazard by vm.infrastructureHazard.collectAsState()
    val hazardBusy by vm.hazardBusy.collectAsState()
    val profile=vm.value("profile","general")
    val official=bundle?.official_alerts.orEmpty().filter { alert->cachedAlertIsActive(alert) && bundle!=null && Freshness.officialAlert(bundle.retrieved_at,alert.expires)!=FreshnessState.STALE }
    val expiredCount=bundle?.official_alerts.orEmpty().size-official.size
    val status=(bundle?.official_status?:bundle?.alerts_status?:"").lowercase()
    LaunchedEffect(bundle?.location?.latitude, bundle?.location?.longitude) {
        if(bundle!=null && hazard==null && !hazardBusy) vm.loadInfrastructureHazard(bundle.location)
    }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal=Space.screen,vertical=Space.lg),verticalArrangement=Arrangement.spacedBy(Space.lg)) {
        SectionHeader(s(R.string.alerts))
        if(profile=="emergency") {
            Surface(color=MaterialTheme.colorScheme.errorContainer,shape=MaterialTheme.shapes.medium,modifier=Modifier.fillMaxWidth()) {
                Text(s(R.string.emergency_priority_banner),modifier=Modifier.padding(Space.xl),style=MaterialTheme.typography.bodyLarge)
            }
        }
        when {
            official.isNotEmpty() -> official.forEach { OfficialAlertCard(it,speak) }
            status=="available" -> {
                Surface(color=MaterialTheme.colorScheme.surface,shape=MaterialTheme.shapes.medium,modifier=Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(Space.xl),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                        Text(s(R.string.alerts_none_active),style=MaterialTheme.typography.titleMedium)
                        Text(s(R.string.alert_help),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            else -> {
                Surface(color=MaterialTheme.colorScheme.surfaceVariant.copy(alpha=0.45f),shape=MaterialTheme.shapes.medium,modifier=Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(Space.xl),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                        Text(s(R.string.alert_unknown),style=MaterialTheme.typography.titleMedium)
                        Text(s(R.string.alert_help),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
        if(expiredCount>0) Text(s(R.string.expired_hidden),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
        Text(s(R.string.offline_alerts),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
        Text(s(R.string.shelter_honesty),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
        QuietButton(s(R.string.open_imd),Icons.AutoMirrored.Filled.OpenInNew,{
            context.startActivity(Intent(Intent.ACTION_VIEW,android.net.Uri.parse("https://mausam.imd.gov.in/")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        })
        QuietButton(s(R.string.open_ndma),Icons.AutoMirrored.Filled.OpenInNew,{
            context.startActivity(Intent(Intent.ACTION_VIEW,android.net.Uri.parse("https://ndma.gov.in/")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        })
        QuietButton(s(R.string.open_sachet),Icons.AutoMirrored.Filled.OpenInNew,{
            context.startActivity(Intent(Intent.ACTION_VIEW,android.net.Uri.parse("https://sachet.ndma.gov.in/")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        })
        QuietButton(s(R.string.disaster_brief_ask),Icons.Default.Search,{
            vm.send("Give me an official-first disaster management situation briefing for responders here.")
        })
        HorizontalDivider(color=MaterialTheme.colorScheme.outline.copy(alpha=0.35f))
        SectionHeader(s(R.string.infra_hazard_title))
        Text(s(R.string.infra_hazard_help),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
        if(hazardBusy && hazard==null) {
            Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(Space.sm)) {
                CircularProgressIndicator(Modifier.size(24.dp));Text(s(R.string.loading))
            }
        }
        hazard?.let { h ->
            Text(h.decision,style=MaterialTheme.typography.titleMedium)
            Text("${s(R.string.infra_hazard_severity)}: ${h.severity} · ${h.label}",style=MaterialTheme.typography.bodyLarge)
            h.inputs?.let { inputs ->
                val bits=buildList {
                    inputs.rain_24h_mm?.let { add("${s(R.string.infra_rain_24h)}: ${it} mm") }
                    inputs.soil_moisture_0_to_7cm?.let { add("${s(R.string.infra_soil)}: $it") }
                    inputs.slope_percent?.let { add("${s(R.string.infra_slope)}: $it%") }
                    inputs.elevation_m?.let { add("${s(R.string.infra_elevation)}: ${it} m") }
                }
                if(bits.isNotEmpty()) Text(bits.joinToString(" · "),style=MaterialTheme.typography.bodyMedium)
            }
            val roads=h.infrastructure?.roads_at_risk_priority.orEmpty()
            if(roads.isNotEmpty()) {
                Text(s(R.string.infra_roads),style=MaterialTheme.typography.titleSmall,fontWeight=FontWeight.Bold)
                roads.take(8).forEach { road ->
                    val label=listOfNotNull(road.name,road.`class`).joinToString(" · ")
                    Text("• $label",style=MaterialTheme.typography.bodyMedium)
                }
            }
            val places=h.infrastructure?.settlements_nearby.orEmpty()
            if(places.isNotEmpty()) {
                Text(s(R.string.infra_settlements),style=MaterialTheme.typography.titleSmall,fontWeight=FontWeight.Bold)
                places.take(8).forEach { placeItem ->
                    Text("• ${placeItem.name ?: placeItem.place}",style=MaterialTheme.typography.bodyMedium)
                }
            }
            Text(h.disclaimer,style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
            QuietButton(s(R.string.ask_road_risk),Icons.Default.Search,{
                vm.send("Will nearby roads or villages be cut off by landslide risk given rainfall, soil moisture and terrain?")
            })
        }
        HorizontalDivider(color=MaterialTheme.colorScheme.outline.copy(alpha=0.35f))
        SectionHeader(s(R.string.risk_estimates))
        Text(s(R.string.risk_help),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
        if(bundle?.risk_estimates.isNullOrEmpty()) Text(s(R.string.no_risk_estimates),style=MaterialTheme.typography.bodyLarge)
        bundle?.risk_estimates.orEmpty().forEach { risk ->
            Column(verticalArrangement=Arrangement.spacedBy(Space.sm),modifier=Modifier.fillMaxWidth()) {
                Row(verticalAlignment=Alignment.CenterVertically) {
                    Icon(Icons.Default.Warning,null,tint=MaterialTheme.colorScheme.error,modifier=Modifier.size(20.dp))
                    Spacer(Modifier.width(Space.sm))
                    Text(s(R.string.weather_risk),style=MaterialTheme.typography.labelLarge)
                }
                Text(risk.message,style=MaterialTheme.typography.titleMedium)
                Text(risk.rationale,style=MaterialTheme.typography.bodyMedium)
                Text(risk.disclaimer,style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
@Composable fun OfficialAlertCard(alert:OfficialAlert,speak:(String,String)->Unit={_,_->}) {
    var open by rememberSaveable(alert.id) { mutableStateOf(true) }
    val language=LocalTranslatedContext.current.resources.configuration.locales[0]?.toLanguageTag() ?: "en-IN"
    Column(verticalArrangement=Arrangement.spacedBy(Space.sm)) {
        AlertSummary(alert,open,{open=!open})
        if(alert.area_match_uncertain==true) {
            Text(s(R.string.area_match_uncertain),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.error)
        }
        TextButton(onClick={
            speak(listOfNotNull(alert.headline,alert.instruction?:alert.description).joinToString(". "), language)
        },modifier=Modifier.heightIn(min=Space.touch)) {
            Icon(Icons.AutoMirrored.Filled.VolumeUp,null,modifier=Modifier.size(20.dp));Spacer(Modifier.width(Space.sm));Text(s(R.string.listen))
        }
    }
}
@Composable fun PlaceDialog(vm:WeatherViewModel,onDismiss:()->Unit,onChoose:(Place,String)->Unit,autoLocate:Boolean=false) {
    var query by rememberSaveable{mutableStateOf("")}
    var locating by remember { mutableStateOf(false) }
    val results by vm.results.collectAsState()
    val saved by vm.savedPlaces.collectAsState()
    val busy by vm.searchBusy.collectAsState()
    val searchError by vm.error.collectAsState()
    val context=LocalContext.current
    val locationUnavailable=s(R.string.location_unavailable)
    val deleteLabel=s(R.string.delete)
    val currentLocationLabel=s(R.string.current_location)
    val purpose=when(vm.value("profile","general")) {
        "farming"->"farm"; "fishing"->"harbour"; "outdoor","vendor"->"work"; else->"home"
    }
    fun useDeviceLocation() {
        locating=true
        DeviceLocation.request(context, onResult = { location ->
            if(location==null) {
                locating=false
                Toast.makeText(context,locationUnavailable,Toast.LENGTH_LONG).show()
            } else {
                vm.resolveCurrentLocation(location.latitude,location.longitude,currentLocationLabel,
                    onResolved={ place -> locating=false; onChoose(place,purpose) },
                    onFailed={
                        locating=false
                        onChoose(Place(currentLocationLabel,location.latitude,location.longitude,"Asia/Kolkata"),purpose)
                    })
            }
        }, timeoutMs=7000L)
    }
    val locationPermission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted->
        if(granted) useDeviceLocation() else Toast.makeText(context,locationUnavailable,Toast.LENGTH_LONG).show()
    }
    AlertDialog(onDismissRequest=onDismiss,title={Text(s(R.string.where_do_you_live),style=MaterialTheme.typography.headlineSmall)},text={
        Column(Modifier.heightIn(max=520.dp).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp)) {
            Text(s(R.string.search_village_first),style=MaterialTheme.typography.bodyLarge)
            OutlinedTextField(query,{query=it.take(80)},label={Text(s(R.string.city_village))},modifier=Modifier.fillMaxWidth().heightIn(min=64.dp),textStyle=MaterialTheme.typography.titleMedium,singleLine=true)
            LaunchedEffect(query) { vm.schedulePlaceSearch(query) }
            BigButton(s(R.string.search),Icons.Default.Search,{vm.search(query)},query.trim().length>=2&&!busy)
            if(locating || busy) Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                CircularProgressIndicator(Modifier.size(28.dp));Text(if(locating) s(R.string.locating) else s(R.string.loading))
            }
            if(searchError=="search_failed"||searchError=="no_places"||searchError=="location_failed") {
                Text(
                    s(when(searchError) {
                        "no_places"->R.string.no_places
                        "search_failed"->R.string.search_failed
                        else->R.string.location_unavailable
                    }),
                    style=MaterialTheme.typography.bodyMedium,
                    color=MaterialTheme.colorScheme.error,
                )
            }
            results.forEach { place->OutlinedButton(onClick={onChoose(place,purpose)},modifier=Modifier.fillMaxWidth().heightIn(min=64.dp)) { Text(place.name,style=MaterialTheme.typography.titleMedium) } }
            Text(s(R.string.or_pick_city),style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)
            listOf(Place("Delhi",28.6139,77.2090),Place("Mumbai",19.0760,72.8777),Place("Bengaluru",12.9716,77.5946),Place("Chennai",13.0827,80.2707),Place("Kolkata",22.5726,88.3639),Place("Lucknow",26.8467,80.9462)).forEach { place ->
                OutlinedButton(onClick={onChoose(place,purpose)},modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)){Text(place.name)}
            }
            if(saved.isNotEmpty()) {
                Text(s(R.string.saved_places),style=MaterialTheme.typography.titleMedium)
                saved.forEach { savedPlace->
                    Column(verticalArrangement=Arrangement.spacedBy(Space.sm),modifier=Modifier.fillMaxWidth()) {
                        Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(Space.sm)) {
                            OutlinedButton(onClick={onChoose(savedPlace.place(),savedPlace.purpose.ifBlank{purpose})},modifier=Modifier.weight(1f).heightIn(min=56.dp)){Text(savedPlace.label,maxLines=4)}
                            IconButton(onClick={vm.deletePlace(savedPlace)},modifier=Modifier.size(Space.touch).semantics{contentDescription=deleteLabel}) {
                                Icon(Icons.Default.Delete,null)
                            }
                        }
                        Text(s(R.string.place_purpose),style=MaterialTheme.typography.bodyMedium)
                        FlowRow(horizontalArrangement=Arrangement.spacedBy(Space.sm),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                            listOf("home" to R.string.purpose_home,"farm" to R.string.purpose_farm,"harbour" to R.string.purpose_harbour,"work" to R.string.purpose_work).forEach { (key,label)->
                                FilterChip(selected=savedPlace.purpose==key,onClick={vm.updatePlacePurpose(savedPlace,key)},label={Text(s(label))},modifier=Modifier.heightIn(min=Space.touch))
                            }
                        }
                    }
                }
            }
            HorizontalDivider()
            BigButton(s(R.string.use_current_location),Icons.Default.MyLocation,{
                if(DeviceLocation.hasPermission(context)) useDeviceLocation()
                else locationPermission.launch(android.Manifest.permission.ACCESS_COARSE_LOCATION)
            },!locating)
            Text(s(R.string.location_backup_help),style=MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(Space.xl))
        }
    },confirmButton={TextButton(onClick=onDismiss){Text(s(R.string.close))}})
}

@Composable fun SettingsScreen(vm:WeatherViewModel,onOpenChat:()->Unit) {
    val prefs by vm.preferences.collectAsState()
    val conversations by vm.conversations.collectAsState()
    fun preference(key:String,default:String="")=prefs[androidx.datastore.preferences.core.stringPreferencesKey(key)]?:default
    var confirm by remember{mutableStateOf(false)}
    var deleteConversationId by remember{mutableStateOf<String?>(null)}
    var server by rememberSaveable{mutableStateOf(preference("server",BuildConfig.API_URL))}
    var advanced by rememberSaveable{mutableStateOf(false)}
    val context=LocalContext.current
    val notificationPermission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted->
        vm.save("risk_notifications",granted.toString()); vm.syncAlertSubscription(granted,ALERT_CHANNEL_RISK)
    }
    val officialNotificationPermission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted->
        vm.save("official_notifications",granted.toString()); vm.syncAlertSubscription(granted,ALERT_CHANNEL_OFFICIAL)
    }
    val languages=listOf("en" to "English","hi" to "हिन्दी","bn" to "বাংলা","te" to "తెలుగు","mr" to "मराठी","ta" to "தமிழ்","gu" to "ગુજરાતી","kn" to "ಕನ್ನಡ","ml" to "മലയാളം","pa" to "ਪੰਜਾਬੀ","or" to "ଓଡ଼ିଆ")
    if(confirm) AlertDialog(onDismissRequest={confirm=false},title={Text(s(R.string.clear_data))},text={Text(s(R.string.clear_help))},confirmButton={TextButton(onClick={vm.clearAll();confirm=false}){Text(s(R.string.delete))}},dismissButton={TextButton(onClick={confirm=false}){Text(s(R.string.cancel))}})
    deleteConversationId?.let { conversationId ->
        AlertDialog(
            onDismissRequest={deleteConversationId=null},
            title={Text(s(R.string.delete_conversation))},
            text={Text(s(R.string.delete_conversation_help))},
            confirmButton={TextButton(onClick={vm.deleteConversation(conversationId);deleteConversationId=null}){Text(s(R.string.delete))}},
            dismissButton={TextButton(onClick={deleteConversationId=null}){Text(s(R.string.cancel))}},
        )
    }
    LazyColumn(contentPadding=PaddingValues(horizontal=Space.screen,vertical=Space.lg),verticalArrangement=Arrangement.spacedBy(Space.md),modifier=Modifier.fillMaxSize()) {
        item { SectionHeader(s(R.string.settings));Text(s(R.string.settings_intro),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        item { Text(s(R.string.theme),style=MaterialTheme.typography.titleMedium,color=MaterialTheme.colorScheme.primary) }
        items(listOf("system" to R.string.system_theme,"light" to R.string.light_theme,"dark" to R.string.dark_theme)) { (key,label)->
            Choice(s(label),preference("theme","system")==key){vm.save("theme",key)}
        }
        item { Row(Modifier.fillMaxWidth().heightIn(min=56.dp).toggleable(value=preference("large")=="true",onValueChange={vm.save("large",it.toString())}),verticalAlignment=Alignment.CenterVertically) {
            Text(s(R.string.large_text),Modifier.weight(1f));Switch(checked=preference("large")=="true",onCheckedChange=null)
        } }
        item { Text(s(R.string.language),style=MaterialTheme.typography.titleMedium,color=MaterialTheme.colorScheme.primary);Text(s(R.string.language_help),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        items(languages) { (key,label)->Choice(label,preference("language","en")==key){vm.save("language",key)} }
        item { Text(s(R.string.use_for),style=MaterialTheme.typography.titleMedium,color=MaterialTheme.colorScheme.primary) }
        items(profileOptions) { (key,label)->Choice(s(label),preference("profile","general")==key){vm.save("profile",key)} }
        item { Text(s(R.string.wifi_only),style=MaterialTheme.typography.titleMedium,color=MaterialTheme.colorScheme.primary) }
        item { Row(Modifier.fillMaxWidth().heightIn(min=56.dp).toggleable(value=preference("wifi","true")=="true",onValueChange={vm.save("wifi",it.toString())}),verticalAlignment=Alignment.CenterVertically) {
            Text(s(R.string.wifi_only),Modifier.weight(1f));Switch(checked=preference("wifi","true")=="true",onCheckedChange=null)
        } }
        item { Row(Modifier.fillMaxWidth().heightIn(min=56.dp).toggleable(value=preference("low_data")=="true",onValueChange={vm.save("low_data",it.toString())}),verticalAlignment=Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text(s(R.string.low_data_mode));Text(s(R.string.low_data_help),style=MaterialTheme.typography.bodyMedium) }
            Switch(checked=preference("low_data")=="true",onCheckedChange=null)
        } }
        item { Text(s(R.string.alert_rules),style=MaterialTheme.typography.titleMedium,color=MaterialTheme.colorScheme.primary) }
        item { Row(Modifier.fillMaxWidth().heightIn(min=56.dp).toggleable(value=preference("risk_notifications")=="true",onValueChange={enabled->
            if(enabled && android.os.Build.VERSION.SDK_INT>=33) notificationPermission.launch(android.Manifest.permission.POST_NOTIFICATIONS) else vm.save("risk_notifications",enabled.toString())
            vm.syncAlertSubscription(enabled,ALERT_CHANNEL_RISK)
        }),verticalAlignment=Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text(s(R.string.risk_notifications));Text(s(R.string.risk_notification_help),style=MaterialTheme.typography.bodyMedium) }
            Switch(checked=preference("risk_notifications")=="true",onCheckedChange=null)
        } }
        item { Row(Modifier.fillMaxWidth().heightIn(min=56.dp).toggleable(value=preference("official_notifications")=="true",onValueChange={enabled->
            if(enabled && android.os.Build.VERSION.SDK_INT>=33) officialNotificationPermission.launch(android.Manifest.permission.POST_NOTIFICATIONS) else vm.save("official_notifications",enabled.toString())
            vm.syncAlertSubscription(enabled,ALERT_CHANNEL_OFFICIAL)
            if(enabled) vm.ensureDeviceRegistration()
        }),verticalAlignment=Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text(s(R.string.official_notifications));Text(s(R.string.official_notification_help),style=MaterialTheme.typography.bodyMedium) }
            Switch(checked=preference("official_notifications")=="true",onCheckedChange=null)
        } }
        item { OutlinedButton(onClick={
            if(android.os.Build.VERSION.SDK_INT>=33 && ContextCompat.checkSelfPermission(context,android.Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED) {
                officialNotificationPermission.launch(android.Manifest.permission.POST_NOTIFICATIONS)
            }
            vm.sendDemoWarning()
        },modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)){Text(s(R.string.demo_warning_action))} }
        item { Text(s(R.string.past_conversations),style=MaterialTheme.typography.titleMedium,color=MaterialTheme.colorScheme.primary) }
        if(conversations.isEmpty()) item { Text(s(R.string.no_conversations),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        items(conversations,key={it.conversationId}) { summary ->
            val whenText=Instant.ofEpochMilli(summary.lastTimestamp).atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("d MMM, h:mm a"))
            Column(Modifier.fillMaxWidth().padding(vertical=Space.sm),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                Text(whenText,style=MaterialTheme.typography.titleMedium)
                Text(String.format(s(R.string.messages_count),summary.messageCount),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                Row(horizontalArrangement=Arrangement.spacedBy(Space.sm),modifier=Modifier.fillMaxWidth()) {
                    if(LocalDensity.current.fontScale>=1.5f) {
                        Column(verticalArrangement=Arrangement.spacedBy(Space.sm),modifier=Modifier.fillMaxWidth()) {
                            OutlinedButton(onClick={vm.openConversation(summary.conversationId);onOpenChat()},modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)){Text(s(R.string.continue_chat),maxLines=3)}
                            TextButton(onClick={deleteConversationId=summary.conversationId},modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)){Text(s(R.string.delete),maxLines=3)}
                        }
                    } else {
                        OutlinedButton(onClick={vm.openConversation(summary.conversationId);onOpenChat()},modifier=Modifier.weight(1f).heightIn(min=52.dp)){Text(s(R.string.continue_chat),maxLines=3)}
                        TextButton(onClick={deleteConversationId=summary.conversationId},modifier=Modifier.weight(1f).heightIn(min=52.dp)){Text(s(R.string.delete),maxLines=3)}
                    }
                }
                HorizontalDivider(color=MaterialTheme.colorScheme.outline.copy(alpha=0.25f))
            }
        }
        item { OutlinedButton(onClick={vm.startNewChat();onOpenChat()},modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)){Text(s(R.string.new_chat))} }
        item { OutlinedButton(onClick={confirm=true},modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)){Text(s(R.string.clear_data))} }
        item { TextButton(onClick={advanced=!advanced},modifier=Modifier.heightIn(min=52.dp)){Text(s(R.string.connection_settings))}
            if(advanced) {
                val online by vm.backendOnline.collectAsState()
                val lastConnected=preference("last_connected").toLongOrNull()
                Text(s(R.string.server_help),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                // Status comes from a real GET /health through the same Retrofit client, never
                // from the fact that a URL is configured.
                Text(vm.base(),style=MaterialTheme.typography.bodyMedium)
                Text(s(when(online){true->R.string.backend_online;false->R.string.backend_offline;else->R.string.connection_unknown}),
                    style=MaterialTheme.typography.titleMedium)
                Text(if(lastConnected==null) s(R.string.connection_never)
                    else s(R.string.connection_last)+Instant.ofEpochMilli(lastConnected).atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("d MMM, h:mm a")),
                    style=MaterialTheme.typography.bodyMedium)
                OutlinedButton(onClick={vm.checkBackend()},modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)){Text(s(R.string.retry_connection))}
                OutlinedTextField(server,{server=it},label={Text(s(R.string.server_url_label))},modifier=Modifier.fillMaxWidth())
                val valid=runCatching{val uri=java.net.URI(server);uri.host!=null && (uri.scheme=="https" || BuildConfig.DEBUG && uri.scheme=="http") && uri.userInfo==null && server.endsWith("/")}.getOrDefault(false)
                Button(onClick={vm.save("server",normalizeBaseUrl(server,BuildConfig.API_URL));vm.checkBackend()},enabled=valid){Text(s(R.string.save))}
            }
        }
    }
}
@Composable fun Choice(label:String,selected:Boolean,onClick:()->Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min=Space.touch).toggleable(value=selected,onValueChange={onClick()}).semantics{this.selected=selected},verticalAlignment=Alignment.CenterVertically) {
        RadioButton(selected=selected,onClick=null);Spacer(Modifier.width(Space.md));Text(label,style=MaterialTheme.typography.bodyLarge,modifier=Modifier.weight(1f))
    }
}





