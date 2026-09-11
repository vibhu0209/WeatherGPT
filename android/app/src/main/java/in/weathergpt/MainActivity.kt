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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
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
                Column(Modifier.statusBarsPadding().padding(horizontal=Space.screen,vertical=Space.md),verticalArrangement=Arrangement.spacedBy(Space.xs)) {
                    Text("WeatherGPT",style=MaterialTheme.typography.labelLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Surface(
                        onClick={showPlace=true},
                        color=MaterialTheme.colorScheme.surface,
                        modifier=Modifier.fillMaxWidth().heightIn(min=Space.touch).semantics { contentDescription=placeAnnouncement; role=Role.Button },
                    ) {
                        Row(verticalAlignment=Alignment.CenterVertically) {
                            Icon(Icons.Default.LocationOn,null,tint=MaterialTheme.colorScheme.primary,modifier=Modifier.size(22.dp))
                            Spacer(Modifier.width(Space.sm))
                            Text(p?.name?:choosePlaceLabel,style=MaterialTheme.typography.titleLarge,modifier=Modifier.weight(1f))
                            Icon(Icons.Default.ExpandMore,null,tint=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        },
    ) { padding ->
        Column(Modifier.padding(padding).imePadding().fillMaxSize()) {
            // One banner per root cause. Stacking "server unreachable", "saved weather" and
            // "could not refresh" told the user three things about a single failure.
            when(noticeFor(failure,b!=null,b?.is_stale==true)) {
                WeatherNotice.NONE->{}
                WeatherNotice.STALE->StatusBanner(s(R.string.saved_notice))
                WeatherNotice.OFFLINE_CACHED->StatusBanner(s(R.string.notice_offline_cached))
                WeatherNotice.CANT_CONNECT->StatusBanner(s(R.string.notice_cant_connect))
                WeatherNotice.PROVIDER_DOWN->StatusBanner(s(R.string.notice_provider_down))
                WeatherNotice.NO_DATA->StatusBanner(s(R.string.notice_no_data))
                WeatherNotice.CHECK_SETTINGS->StatusBanner(s(R.string.notice_check_settings))
            }
            if(error=="no_places"||error=="search_failed"||error=="location_failed")
                StatusBanner(s(when(error){"no_places"->R.string.no_places;"search_failed"->R.string.search_failed;else->R.string.location_unavailable}))
            if(busy) LinearProgressIndicator(Modifier.fillMaxWidth().semantics{contentDescription=loadingLabel})
            when(tab) {
                0 -> ChatScreen(vm,p,b,busy,chatStatus,{showPlace=true},::speak)
                1 -> HomeScreen(vm,b,busy,{vm.refresh()},{showPlace=true},onAsk={tab=0},onRetryConnection={vm.checkBackend()})
                2 -> ForecastScreen(b,busy,failure,{vm.refresh()},{showPlace=true})
                3 -> AlertScreen(b,::speak)
                else -> SettingsScreen(vm,onOpenChat={tab=0})
            }
        }
    }
}

@Composable fun HomeScreen(vm:WeatherViewModel,b:BundleDto?,busy:Boolean,refresh:()->Unit,choose:()->Unit,onAsk:()->Unit,onRetryConnection:()->Unit) {
    val profile=vm.value("profile","general")
    val score=b?.scores?.get(profile)
    val advice=b?.recommendations?.get(profile).orEmpty()
    val failure by vm.failure.collectAsState()
    var alertOpen by rememberSaveable { mutableStateOf(false) }
    val locale=Locale.getDefault()
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(horizontal=Space.screen,vertical=Space.lg),verticalArrangement=Arrangement.spacedBy(Space.xl)) {
        if(b==null) {
            if(failure==NetFailure.NONE) item { Text(s(R.string.no_saved),style=MaterialTheme.typography.bodyLarge) }
            item { PrimaryWeatherButton(s(R.string.search),Icons.Default.Search,choose) }
            item { QuietButton(s(R.string.retry_connection),Icons.Default.Refresh,onRetryConnection) }
        } else {
            val hour=nearestHour(b)
            item {
                val temp=hour?.temperature?.let { "${it}°C" }
                val condition=conditionResource(hour?.weather_code?.toInt())?.let { s(it) }
                val feels=hour?.apparent_temperature?.let { "${s(R.string.feels_like)} ${it}°C" }
                Column(
                    Modifier.semantics(mergeDescendants=true) { contentDescription=listOfNotNull(temp,condition,feels).joinToString(", ") },
                    verticalArrangement=Arrangement.spacedBy(Space.sm),
                ) {
                    Text("${s(R.string.updated)} ${ageMinutes(b.retrieved_at)} ${s(R.string.minutes_ago)}",style=MaterialTheme.typography.labelLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    if(hour?.temperature!=null) Text("${hour.temperature}°C",style=MaterialTheme.typography.displayLarge)
                    conditionResource(hour?.weather_code?.toInt())?.let{Text(s(it),style=MaterialTheme.typography.titleLarge)}
                    if(hour?.apparent_temperature!=null) Text("${s(R.string.feels_like)} ${hour.apparent_temperature}°C",style=MaterialTheme.typography.bodyLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            item { Text(s(R.string.home_intro),style=MaterialTheme.typography.bodyLarge,color=MaterialTheme.colorScheme.onSurfaceVariant) }
            if(score!=null) item { WeatherScoreCard(score) }
            item {
                val stackMetrics=LocalDensity.current.fontScale>=1.5f
                if(stackMetrics) {
                    Column(Modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(Space.md)) {
                        WeatherMetric(s(R.string.rain),hour?.rain_chance?.let{"$it%"}?:s(R.string.unavailable),Modifier.fillMaxWidth())
                        WeatherMetric(s(R.string.wind),formatWindKmh(hour?.wind_ms,locale)?.let{"$it ${s(R.string.unit_kmh)}"}?:s(R.string.unavailable),Modifier.fillMaxWidth())
                        WeatherMetric(s(R.string.humidity),hour?.humidity?.let{"$it%"}?:s(R.string.unavailable),Modifier.fillMaxWidth())
                    }
                } else {
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(Space.md)) {
                        WeatherMetric(s(R.string.rain),hour?.rain_chance?.let{"$it%"}?:s(R.string.unavailable),Modifier.weight(1f))
                        WeatherMetric(s(R.string.wind),formatWindKmh(hour?.wind_ms,locale)?.let{"$it ${s(R.string.unit_kmh)}"}?:s(R.string.unavailable),Modifier.weight(1f))
                        WeatherMetric(s(R.string.humidity),hour?.humidity?.let{"$it%"}?:s(R.string.unavailable),Modifier.weight(1f))
                    }
                }
            }
            if(advice.isNotEmpty()) item {
                Column(verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                    Text(s(R.string.your_advice),style=MaterialTheme.typography.titleMedium)
                    advice.take(2).forEach { Text(it.message,style=MaterialTheme.typography.bodyLarge) }
                }
            }
            val activeOfficial=b.official_alerts.orEmpty().filter { cachedAlertIsActive(it) && Freshness.officialAlert(b.retrieved_at,it.expires)!=FreshnessState.STALE }
            item {
                val status=(b.official_status?:b.alerts_status?:"").lowercase()
                Column(verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                    Text(s(R.string.home_alerts),style=MaterialTheme.typography.titleMedium)
                    if(activeOfficial.isNotEmpty()) AlertSummary(activeOfficial.first(),alertOpen,{alertOpen=!alertOpen})
                    else Text(s(if(status=="available") R.string.alerts_none_active else R.string.alert_unknown),style=MaterialTheme.typography.bodyLarge)
                    b.risk_estimates.orEmpty().firstOrNull()?.let { risk ->
                        Text(s(R.string.weather_risk),style=MaterialTheme.typography.labelLarge)
                        Text(risk.message,style=MaterialTheme.typography.bodyLarge)
                    }
                }
            }
            item { PrimaryWeatherButton(s(R.string.ask_weathergpt),Icons.Default.Mic,onAsk) }
            item { QuietButton(s(R.string.download),Icons.Default.Refresh,refresh,!busy) }
        }
    }
}
@Composable fun BigButton(label:String,icon:androidx.compose.ui.graphics.vector.ImageVector,onClick:()->Unit,enabled:Boolean=true) {
    PrimaryWeatherButton(label,icon,onClick,enabled)
}
fun conditionResource(code:Int?):Int?=when(code) { 0->R.string.clear_sky;1,2,3->R.string.cloudy;45,48->R.string.fog;51,53,55,56,57->R.string.drizzle;61,63,65,66,67->R.string.rainy;71,73,75,77->R.string.snow;80,81,82,85,86->R.string.showers;95,96,99->R.string.thunderstorm;else->null }

@Composable fun ChatScreen(vm:WeatherViewModel,p:Place?,b:BundleDto?,busy:Boolean,chatStatus:String,choose:()->Unit,speak:(String,String)->Unit) {
    val messages by vm.messages.collectAsState()
    val compare by vm.comparePlace.collectAsState()
    val saved by vm.savedPlaces.collectAsState()
    var draft by rememberSaveable { mutableStateOf("") }
    val context=LocalContext.current
    val unavailable=s(R.string.voice_unavailable)
    val suggestionIds=when(vm.value("profile","general")) {
        "farming" -> listOf(R.string.rain_question,R.string.farm_work_question,R.string.spray_question,R.string.warning_question)
        "fishing" -> listOf(R.string.marine_question,R.string.wave_question,R.string.warning_question)
        "research" -> listOf(R.string.climate_question,R.string.tomorrow_question,R.string.warning_question)
        else -> listOf(R.string.rain_question,R.string.next_hours_question,R.string.tomorrow_question,R.string.warning_question)
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
    Column(Modifier.fillMaxSize()) {
        if(chatStatus.isNotEmpty()) StatusBanner(s(if(chatStatus=="sending") R.string.sending_question else R.string.checking_sources))
        LazyColumn(Modifier.weight(1f).fillMaxWidth(),contentPadding=PaddingValues(Space.screen),verticalArrangement=Arrangement.spacedBy(Space.md),reverseLayout=true) {
            items(messages.reversed(),key={it.id}) { m ->
                val user=m.role=="user"
                val split=if(!user) m.text.split("\n\n$downloaded") else listOf(m.text)
                val body=split.first()
                val meta=if(split.size>1) downloaded+split.drop(1).joinToString("\n\n$downloaded") else null
                var open by rememberSaveable(m.id) { mutableStateOf(false) }
                Row(Modifier.fillMaxWidth().wrapContentHeight(unbounded=true),horizontalArrangement=if(user) Arrangement.End else Arrangement.Start) {
                    Surface(
                        color=if(user) MaterialTheme.colorScheme.surfaceVariant else MaterialTheme.colorScheme.surface,
                        shape=MaterialTheme.shapes.medium,
                        tonalElevation=if(user) 0.dp else 1.dp,
                        modifier=Modifier.fillMaxWidth(if(user) 0.86f else 0.94f),
                    ) {
                        Column(Modifier.padding(Space.lg),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                            Column(Modifier.semantics(mergeDescendants=true){}) {
                                Text(if(user) s(R.string.you) else "WeatherGPT",style=MaterialTheme.typography.labelLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(body,style=MaterialTheme.typography.bodyLarge)
                            }
                            if(!user) {
                                FlowRow(verticalArrangement=Arrangement.spacedBy(Space.xs),horizontalArrangement=Arrangement.spacedBy(Space.sm)) {
                                    TextButton(onClick={speak(m.text,m.language)},modifier=Modifier.heightIn(min=Space.touch)) {
                                        Icon(Icons.AutoMirrored.Filled.VolumeUp,null,modifier=Modifier.size(20.dp));Spacer(Modifier.width(Space.sm));Text(s(R.string.listen))
                                    }
                                    if(meta!=null) TextButton(onClick={open=!open},modifier=Modifier.heightIn(min=Space.touch)) {
                                        Text(s(if(open) R.string.hide_details else R.string.show_details))
                                    }
                                }
                                if(open && meta!=null) Text(meta,style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
            }
            if(messages.isEmpty()) item {
                Column(verticalArrangement=Arrangement.spacedBy(Space.md)) {
                    Text(s(R.string.welcome),style=MaterialTheme.typography.headlineSmall)
                    Text(s(R.string.intro),style=MaterialTheme.typography.bodyLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(s(R.string.tap_to_ask),style=MaterialTheme.typography.bodyLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    if(p==null) PrimaryWeatherButton(s(R.string.search),Icons.Default.Search,choose)
                    else FlowRow(horizontalArrangement=Arrangement.spacedBy(Space.sm),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                        suggestionIds.forEach { id-> val prompt=s(id); SuggestionChip(prompt,!busy){sendChat(prompt)} }
                    }
                }
            }
        }
        if(p!=null) Surface(color=MaterialTheme.colorScheme.surface,tonalElevation=1.dp) {
            Column(Modifier.padding(horizontal=Space.screen,vertical=Space.md),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
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
                if(messages.isNotEmpty() && LocalDensity.current.fontScale<1.5f) FlowRow(horizontalArrangement=Arrangement.spacedBy(Space.sm),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                    listOf(
                        R.string.action_hourly to R.string.next_hours_question,
                        R.string.action_warnings to R.string.warning_question,
                        R.string.action_score to R.string.weather_score,
                    ).forEach { (label,prompt) ->
                        val question=s(prompt)
                        SuggestionChip(s(label),!busy){sendChat(question)}
                    }
                }
                Row(verticalAlignment=Alignment.Bottom,horizontalArrangement=Arrangement.spacedBy(Space.sm)) {
                    OutlinedTextField(value=draft,onValueChange={draft=it.take(1000)},placeholder={Text(typeQuestion)},modifier=Modifier.weight(1f).heightIn(min=Space.touch),textStyle=MaterialTheme.typography.bodyLarge,maxLines=3,shape=MaterialTheme.shapes.medium)
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
@Composable fun WeatherCard(b:BundleDto) {
    var details by rememberSaveable(b.retrieved_at) { mutableStateOf(false) }
    val hour=nearestHour(b)
    val locale=Locale.getDefault()
    Column(verticalArrangement=Arrangement.spacedBy(Space.sm)) {
        if(hour?.temperature!=null) Text("${hour.temperature}°C",style=MaterialTheme.typography.displayMedium)
        conditionResource(hour?.weather_code?.toInt())?.let{Text(s(it),style=MaterialTheme.typography.titleMedium)}
        Text("${s(R.string.updated)} ${ageMinutes(b.retrieved_at)} ${s(R.string.minutes_ago)}",style=MaterialTheme.typography.labelLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
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
            if(b.agreement=="sources_disagree") Text(s(R.string.disagree),style=MaterialTheme.typography.bodyMedium)
            b.confidence?.let { confidence ->
                Text("${s(R.string.forecast_confidence)}: ${confidence.score}/100 · ${confidence.label}",style=MaterialTheme.typography.bodyMedium)
                confidence.reasons.forEach { Text("• $it",style=MaterialTheme.typography.bodyMedium) }
                Text(s(R.string.confidence_help),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
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
            item { WeatherCard(b) }
            item { QuietButton(s(R.string.download),Icons.Default.Download,refresh,!busy) }
            if(b.daily.orEmpty().isNotEmpty()) {
                items(b.daily.orEmpty()) { day ->
                    val rainLabel=s(R.string.rain)
                    val unavailable=s(R.string.unavailable)
                    val range="${day.temperature_min?.let{"$it°"}?:unavailable} / ${day.temperature_max?.let{"$it°"}?:unavailable}"
                    val rain=day.rain_chance_max?.let{"$it%"}?:unavailable
                    Column(
                        Modifier.fillMaxWidth().padding(vertical=Space.sm).semantics(mergeDescendants=true) {
                            contentDescription=dailyForecastTalkBack(day.date,range,rainLabel,rain)
                        },
                        verticalArrangement=Arrangement.spacedBy(Space.xs),
                    ) {
                        Text(day.date,style=MaterialTheme.typography.titleMedium)
                        Text(range,style=MaterialTheme.typography.bodyLarge)
                        Text(rain,style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    HorizontalDivider(color=MaterialTheme.colorScheme.outline.copy(alpha=0.35f))
                }
            }
            item { Text(s(R.string.hourly),style=MaterialTheme.typography.titleMedium) }
            val hours=b.hourly.filter{Instant.parse(it.time)>Instant.now().minusSeconds(3600)}.take(24)
            item {
                val rainLabel=s(R.string.rain)
                val unavailable=s(R.string.unavailable)
                val hourMin=(72f*LocalDensity.current.fontScale.coerceAtLeast(1f)).dp
                FlowRow(horizontalArrangement=Arrangement.spacedBy(Space.sm),verticalArrangement=Arrangement.spacedBy(Space.sm)) {
                    hours.forEach { h ->
                        val timeLabel=Instant.parse(h.time).atZone(ZoneId.of(b.location.timezone)).format(DateTimeFormatter.ofPattern("h a"))
                        val temp=h.temperature?.let{"${it.toInt()}°C"}?:unavailable
                        val rain=h.rain_chance?.let{"${it.toInt()}%"}?:"—"
                        Column(
                            Modifier.widthIn(min=hourMin).padding(vertical=Space.sm).semantics(mergeDescendants=true) {
                                contentDescription=hourlyTalkBack(timeLabel,temp,rainLabel,rain)
                            },
                            verticalArrangement=Arrangement.spacedBy(Space.xs),
                        ) {
                            Text(timeLabel,style=MaterialTheme.typography.labelLarge,color=MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(h.temperature?.let{"${it.toInt()}°"}?:unavailable,style=MaterialTheme.typography.titleMedium)
                            Text(h.rain_chance?.let{"${it.toInt()}%"}?:"—",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
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
@Composable fun AlertScreen(bundle:BundleDto?,speak:(String,String)->Unit={_,_->}) {
    val context=LocalContext.current
    val official=bundle?.official_alerts.orEmpty().filter { alert->cachedAlertIsActive(alert) && bundle!=null && Freshness.officialAlert(bundle.retrieved_at,alert.expires)!=FreshnessState.STALE }
    val expiredCount=bundle?.official_alerts.orEmpty().size-official.size
    val status=(bundle?.official_status?:bundle?.alerts_status?:"").lowercase()
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal=Space.screen,vertical=Space.lg),verticalArrangement=Arrangement.spacedBy(Space.lg)) {
        SectionHeader(s(R.string.alerts))
        when {
            official.isNotEmpty() -> official.forEach { OfficialAlertCard(it,speak) }
            status=="available" -> {
                Text(s(R.string.alerts_none_active),style=MaterialTheme.typography.bodyLarge)
                Text(s(R.string.alert_help),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }
            else -> {
                Text(s(R.string.alert_unknown),style=MaterialTheme.typography.bodyLarge)
                Text(s(R.string.alert_help),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        if(expiredCount>0) Text(s(R.string.expired_hidden),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
        Text(s(R.string.offline_alerts),style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
        QuietButton(s(R.string.open_imd),Icons.AutoMirrored.Filled.OpenInNew,{
            context.startActivity(Intent(Intent.ACTION_VIEW,android.net.Uri.parse("https://mausam.imd.gov.in/")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        })
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
            BigButton(s(R.string.search),Icons.Default.Search,{vm.search(query)},query.trim().length>=2&&!busy)
            if(locating || busy) Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                CircularProgressIndicator(Modifier.size(28.dp));Text(if(locating) s(R.string.locating) else s(R.string.loading))
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
        item { SectionHeader(s(R.string.settings));Text(s(R.string.settings_intro)) }
        item { Text(s(R.string.theme),style=MaterialTheme.typography.titleLarge) }
        items(listOf("system" to R.string.system_theme,"light" to R.string.light_theme,"dark" to R.string.dark_theme)) { (key,label)->
            Choice(s(label),preference("theme","system")==key){vm.save("theme",key)}
        }
        item { Row(Modifier.fillMaxWidth().heightIn(min=56.dp).toggleable(value=preference("large")=="true",onValueChange={vm.save("large",it.toString())}),verticalAlignment=Alignment.CenterVertically) {
            Text(s(R.string.large_text),Modifier.weight(1f));Switch(checked=preference("large")=="true",onCheckedChange=null)
        } }
        item { Row(Modifier.fillMaxWidth().heightIn(min=56.dp).toggleable(value=preference("wifi","true")=="true",onValueChange={vm.save("wifi",it.toString())}),verticalAlignment=Alignment.CenterVertically) {
            Text(s(R.string.wifi_only),Modifier.weight(1f));Switch(checked=preference("wifi","true")=="true",onCheckedChange=null)
        } }
        item { Row(Modifier.fillMaxWidth().heightIn(min=56.dp).toggleable(value=preference("low_data")=="true",onValueChange={vm.save("low_data",it.toString())}),verticalAlignment=Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text(s(R.string.low_data_mode));Text(s(R.string.low_data_help),style=MaterialTheme.typography.bodyMedium) }
            Switch(checked=preference("low_data")=="true",onCheckedChange=null)
        } }
        item { Text(s(R.string.alert_rules),style=MaterialTheme.typography.titleLarge) }
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
        item { Text(s(R.string.language),style=MaterialTheme.typography.titleLarge);Text(s(R.string.language_help),style=MaterialTheme.typography.bodyMedium) }
        items(languages) { (key,label)->Choice(label,preference("language","en")==key){vm.save("language",key)} }
        item { Text(s(R.string.use_for),style=MaterialTheme.typography.titleLarge) }
        items(profileOptions) { (key,label)->Choice(s(label),preference("profile","general")==key){vm.save("profile",key)} }
        item { Text(s(R.string.past_conversations),style=MaterialTheme.typography.titleLarge) }
        if(conversations.isEmpty()) item { Text(s(R.string.no_conversations),style=MaterialTheme.typography.bodyMedium) }
        items(conversations,key={it.conversationId}) { summary ->
            val whenText=Instant.ofEpochMilli(summary.lastTimestamp).atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("d MMM, h:mm a"))
            OutlinedCard(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                    Text(whenText,style=MaterialTheme.typography.titleMedium)
                    Text(String.format(s(R.string.messages_count),summary.messageCount),style=MaterialTheme.typography.bodyMedium)
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp),modifier=Modifier.fillMaxWidth()) {
                        if(LocalDensity.current.fontScale>=1.5f) {
                            Column(verticalArrangement=Arrangement.spacedBy(8.dp),modifier=Modifier.fillMaxWidth()) {
                                OutlinedButton(onClick={vm.openConversation(summary.conversationId);onOpenChat()},modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)){Text(s(R.string.continue_chat),maxLines=3)}
                                OutlinedButton(onClick={deleteConversationId=summary.conversationId},modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)){Text(s(R.string.delete),maxLines=3)}
                            }
                        } else {
                            OutlinedButton(onClick={vm.openConversation(summary.conversationId);onOpenChat()},modifier=Modifier.weight(1f).heightIn(min=52.dp)){Text(s(R.string.continue_chat),maxLines=3)}
                            OutlinedButton(onClick={deleteConversationId=summary.conversationId},modifier=Modifier.weight(1f).heightIn(min=52.dp)){Text(s(R.string.delete),maxLines=3)}
                        }
                    }
                }
            }
        }
        item { OutlinedButton(onClick={vm.startNewChat();onOpenChat()},modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)){Text(s(R.string.new_chat))} }
        item { OutlinedButton(onClick={confirm=true},modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)){Text(s(R.string.clear_data))} }
        item { TextButton(onClick={advanced=!advanced},modifier=Modifier.heightIn(min=52.dp)){Text(s(R.string.connection_settings))}
            if(advanced) {
                val online by vm.backendOnline.collectAsState()
                val lastConnected=preference("last_connected").toLongOrNull()
                Text(s(R.string.server_help))
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








