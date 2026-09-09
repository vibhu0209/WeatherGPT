package `in`.weathergpt

import android.app.Activity
import android.content.Intent
import android.content.Context
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.location.LocationManager
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.*
import androidx.lifecycle.viewmodel.compose.viewModel
import java.time.*
import java.time.format.DateTimeFormatter
import java.util.Locale

class MainActivity:ComponentActivity() {
    override fun onCreate(savedInstanceState:Bundle?) { super.onCreate(savedInstanceState); enableEdgeToEdge(); setContent { WeatherApp() } }
}
private val LocalTranslatedContext=staticCompositionLocalOf<Context>{error("Translated context is unavailable")}
private val profileOptions=listOf("general" to R.string.general,"farming" to R.string.farming,"fishing" to R.string.fishing,"outdoor" to R.string.outdoor,"tourism" to R.string.tourism,"transport" to R.string.transport,"construction" to R.string.construction,"emergency" to R.string.emergency,"vendor" to R.string.vendor,"aviation" to R.string.aviation,"research" to R.string.research)
@Composable fun s(id:Int)=LocalTranslatedContext.current.resources.getString(id)
private val Light=lightColorScheme(primary=Color(0xFF08695B),onPrimary=Color.White,primaryContainer=Color(0xFFD8F3E8),onPrimaryContainer=Color(0xFF123E34),background=Color(0xFFF8FAF6),surface=Color(0xFFF8FAF6),surfaceVariant=Color(0xFFE6EBE5),onSurface=Color(0xFF172B26),onSurfaceVariant=Color(0xFF40554D),secondaryContainer=Color(0xFFE2F2FF),onSecondaryContainer=Color(0xFF173A4A),tertiaryContainer=Color(0xFFFFE0B2),onTertiaryContainer=Color(0xFF4A2800))
private val Dark=darkColorScheme(primary=Color(0xFF8BD6BA),onPrimary=Color(0xFF073B2E),primaryContainer=Color(0xFF204C3D),onPrimaryContainer=Color(0xFFC4F2DC),background=Color(0xFF111C18),surface=Color(0xFF111C18),surfaceVariant=Color(0xFF293B32),onSurface=Color(0xFFE5EFE8),onSurfaceVariant=Color(0xFFC0D0C5),secondaryContainer=Color(0xFF29424E),onSecondaryContainer=Color(0xFFD7F1FF),tertiaryContainer=Color(0xFF5A3A10),onTertiaryContainer=Color(0xFFFFE0B2))

@Composable fun WeatherApp(vm:WeatherViewModel=viewModel()) {
    val prefs by vm.preferences.collectAsState()
    val lang=prefs[androidx.datastore.preferences.core.stringPreferencesKey("language")]?:"en"
    val theme=prefs[androidx.datastore.preferences.core.stringPreferencesKey("theme")]?:"system"
    val large=prefs[androidx.datastore.preferences.core.stringPreferencesKey("large")] == "true"
    val original=LocalContext.current
    val currentConfiguration=LocalConfiguration.current
    val config=Configuration(currentConfiguration).apply{setLocale(Locale.forLanguageTag(lang))}
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
        MaterialTheme(colorScheme=if(dark) Dark else Light,
            typography=Typography(bodyLarge=androidx.compose.ui.text.TextStyle(fontSize=18.sp,lineHeight=27.sp),bodyMedium=androidx.compose.ui.text.TextStyle(fontSize=16.sp,lineHeight=24.sp))) {
            Surface(Modifier.fillMaxSize()) { AppContent(vm) }
        }
    }
}

@Composable fun AppContent(vm:WeatherViewModel) {
    var tab by rememberSaveable { mutableStateOf(0) }
    var showPlace by rememberSaveable { mutableStateOf(false) }
    val p by vm.place.collectAsState()
    val b by vm.weather.collectAsState()
    val busy by vm.busy.collectAsState()
    val offline by vm.offline.collectAsState()
    val error by vm.error.collectAsState()
    val chatStatus by vm.chatStatus.collectAsState()
    val context=LocalContext.current
    val prefs by vm.preferences.collectAsState()
    if(prefs[androidx.datastore.preferences.core.stringPreferencesKey("onboarded")]!="true") {
        var chosen by rememberSaveable { mutableStateOf(vm.value("language","en")) }
        var chosenProfile by rememberSaveable { mutableStateOf(vm.value("profile","general")) }
        AlertDialog(onDismissRequest={},title={Text("Welcome · नमस्ते")},text={
            Column(Modifier.heightIn(max=400.dp).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                Text("Choose your language · अपनी भाषा चुनें")
                listOf("en" to "English","hi" to "हिन्दी","bn" to "বাংলা","te" to "తెలుగు","mr" to "मराठी","ta" to "தமிழ்","gu" to "ગુજરાતી","kn" to "ಕನ್ನಡ","ml" to "മലയാളം","pa" to "ਪੰਜਾਬੀ","or" to "ଓଡ଼ିଆ").forEach { (code,name)->Choice(name,chosen==code){chosen=code;vm.save("language",code)} }
                HorizontalDivider()
                Text(s(R.string.use_for),style=MaterialTheme.typography.titleMedium)
                profileOptions.forEach { (key,label)->Choice(s(label),chosenProfile==key){chosenProfile=key;vm.save("profile",key)} }
            }
        },confirmButton={TextButton(onClick={vm.save("onboarded","true");showPlace=true}){Text(s(R.string.choose_place))}})
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
        if(!ttsReady || engine==null || engine.setLanguage(Locale.forLanguageTag(language))<0) {
            Toast.makeText(context,noVoice,Toast.LENGTH_LONG).show();return
        }
        engine.speak(text,TextToSpeech.QUEUE_FLUSH,null,"answer")
    }
    if(showPlace) PlaceDialog(vm,onDismiss={showPlace=false},onChoose={vm.choose(it);showPlace=false})
    Scaffold(
        bottomBar={ NavigationBar {
            listOf(R.string.chat to Icons.Default.ChatBubbleOutline,R.string.home to Icons.Default.Home,R.string.forecast to Icons.Default.WbSunny,R.string.alerts to Icons.Default.NotificationsNone,R.string.settings to Icons.Default.Settings).forEachIndexed { index,(label,icon)->
                NavigationBarItem(selected=tab==index,onClick={tab=index},icon={Icon(icon,null)},label={Text(s(label))})
            }
        } },
        topBar={ Column(Modifier.statusBarsPadding().padding(horizontal=20.dp,vertical=12.dp)) {
            Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                Icon(Icons.Default.WbSunny,null,tint=MaterialTheme.colorScheme.primary,modifier=Modifier.size(30.dp))
                Spacer(Modifier.width(10.dp));Text("WeatherGPT",style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold)
            }
            TextButton(onClick={showPlace=true},modifier=Modifier.heightIn(min=52.dp)) {
                Icon(Icons.Default.LocationOn,null);Spacer(Modifier.width(6.dp));Text(p?.name?:s(R.string.choose_place));Icon(Icons.Default.ExpandMore,null)
            }
        } }
    ) { padding ->
        Column(Modifier.padding(padding).imePadding().fillMaxSize()) {
            if(offline || b?.is_stale==true) Notice(s(R.string.saved_notice))
            if(error.isNotEmpty()) Notice(s(when(error){"no_places"->R.string.no_places;"search_failed"->R.string.search_failed;"location_failed"->R.string.location_unavailable;else->R.string.refresh_failed}))
            if(busy) LinearProgressIndicator(Modifier.fillMaxWidth().semantics{contentDescription=context.getString(R.string.loading)})
            when(tab) {
                0 -> ChatScreen(vm,p,b,busy,chatStatus,{showPlace=true},::speak)
                1 -> HomeScreen(vm,b,busy,{vm.refresh()},{showPlace=true})
                2 -> ForecastScreen(b,busy,{vm.refresh()},{showPlace=true})
                3 -> AlertScreen(b)
                else -> SettingsScreen(vm,onOpenChat={tab=0})
            }
        }
    }
}
@Composable fun HomeScreen(vm:WeatherViewModel,b:BundleDto?,busy:Boolean,refresh:()->Unit,choose:()->Unit) {
    val profile=vm.value("profile","general")
    val score=b?.scores?.get(profile)
    val advice=b?.recommendations?.get(profile).orEmpty()
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
        item { Heading(s(R.string.home));Text(s(R.string.home_intro),style=MaterialTheme.typography.bodyLarge) }
        if(b==null) item { Text(s(R.string.no_saved));BigButton(s(R.string.choose_place),Icons.Default.LocationOn,choose) }
        else {
            val activeOfficial=b.official_alerts.orEmpty().filter { Freshness.officialAlert(b.retrieved_at,it.expires)!=FreshnessState.STALE }
            if(activeOfficial.isNotEmpty()) item { OfficialAlertCard(activeOfficial.first()) }
            item { WeatherCard(b) }
            item { Surface(color=MaterialTheme.colorScheme.primaryContainer,shape=RoundedCornerShape(24.dp),modifier=Modifier.fillMaxWidth()) {
                Column(Modifier.padding(22.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                    Text(s(R.string.weather_score),style=MaterialTheme.typography.titleMedium)
                    Text(score?.score?.toString()?:s(R.string.unavailable),style=MaterialTheme.typography.displayMedium,fontWeight=FontWeight.Bold)
                    Text(score?.label?:s(R.string.unavailable),style=MaterialTheme.typography.titleLarge)
                    score?.limiting_factors.orEmpty().forEach { Text("• $it") }
                    Text(score?.disclaimer?:s(R.string.score_disclaimer),style=MaterialTheme.typography.bodyMedium)
                }
            } }
            if(advice.isNotEmpty()) item { Column(verticalArrangement=Arrangement.spacedBy(10.dp)) {
                Text(s(R.string.your_advice),style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold)
                advice.forEach { item->OutlinedCard(Modifier.fillMaxWidth()){Text(item.message,Modifier.padding(16.dp),style=MaterialTheme.typography.bodyLarge)} }
            } }
            item { BigButton(s(R.string.download),Icons.Default.Refresh,refresh,!busy) }
        }
    }
}
@Composable fun Notice(text:String) { Surface(color=MaterialTheme.colorScheme.secondaryContainer) { Text(text,Modifier.fillMaxWidth().padding(16.dp),style=MaterialTheme.typography.bodyMedium) } }
@Composable fun BigButton(label:String,icon:androidx.compose.ui.graphics.vector.ImageVector,onClick:()->Unit,enabled:Boolean=true) {
    Button(onClick=onClick,enabled=enabled,modifier=Modifier.fillMaxWidth().heightIn(min=56.dp),shape=RoundedCornerShape(16.dp),contentPadding=PaddingValues(16.dp)) {
        Icon(icon,null);Spacer(Modifier.width(10.dp));Text(label,style=MaterialTheme.typography.titleMedium)
    }
}
@Composable fun Heading(text:String) { Text(text,style=MaterialTheme.typography.headlineSmall,fontWeight=FontWeight.Bold,modifier=Modifier.semantics{heading()}) }
fun conditionResource(code:Int?):Int?=when(code) { 0->R.string.clear_sky;1,2,3->R.string.cloudy;45,48->R.string.fog;51,53,55,56,57->R.string.drizzle;61,63,65,66,67->R.string.rainy;71,73,75,77->R.string.snow;80,81,82,85,86->R.string.showers;95,96,99->R.string.thunderstorm;else->null }

@Composable fun ChatScreen(vm:WeatherViewModel,p:Place?,b:BundleDto?,busy:Boolean,chatStatus:String,choose:()->Unit,speak:(String,String)->Unit) {
    val messages by vm.messages.collectAsState()
    var draft by rememberSaveable { mutableStateOf("") }
    val context=LocalContext.current
    val unavailable=s(R.string.voice_unavailable)
    val suggestionIds=when(vm.value("profile","general")) {
        "farming" -> listOf(R.string.farm_work_question,R.string.spray_question,R.string.rain_question,R.string.warning_question)
        "fishing" -> listOf(R.string.marine_question,R.string.wave_question,R.string.warning_question,R.string.tomorrow_question)
        "outdoor","construction","transport","vendor" -> listOf(R.string.next_hours_question,R.string.tomorrow_question,R.string.rain_question,R.string.warning_question)
        "tourism" -> listOf(R.string.tomorrow_question,R.string.next_hours_question,R.string.rain_question,R.string.climate_question)
        "emergency","aviation" -> listOf(R.string.warning_question,R.string.next_hours_question,R.string.tomorrow_question,R.string.rain_question)
        else -> listOf(R.string.rain_question,R.string.tomorrow_question,R.string.warning_question,R.string.climate_question)
    }
    val launcher=rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result->
        if(result.resultCode==Activity.RESULT_OK) draft=result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()?.take(1000)?:draft
    }
    Column(Modifier.fillMaxSize()) {
        if(chatStatus.isNotEmpty()) Notice(s(if(chatStatus=="sending") R.string.sending_question else R.string.checking_sources))
        LazyColumn(Modifier.weight(1f).fillMaxWidth(),contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp),reverseLayout=true) {
            items(messages.reversed(),key={it.id}) { m ->
                Surface(color=if(m.role=="user") MaterialTheme.colorScheme.surfaceVariant else MaterialTheme.colorScheme.primaryContainer,shape=RoundedCornerShape(20.dp),modifier=Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(20.dp)) {
                        Text(if(m.role=="user") s(R.string.you) else "WeatherGPT",style=MaterialTheme.typography.labelLarge,fontWeight=FontWeight.Bold)
                        Spacer(Modifier.height(8.dp));Text(m.text,style=MaterialTheme.typography.bodyLarge)
                        if(m.role!="user") TextButton(onClick={speak(m.text,m.language)},modifier=Modifier.heightIn(min=52.dp)) { Icon(Icons.AutoMirrored.Filled.VolumeUp,null);Spacer(Modifier.width(8.dp));Text(s(R.string.listen)) }
                    }
                }
            }
            item { Column(verticalArrangement=Arrangement.spacedBy(16.dp)) {
                Text(s(R.string.welcome_tag),color=MaterialTheme.colorScheme.primary,style=MaterialTheme.typography.labelLarge)
                Heading(s(R.string.welcome))
                Text(s(R.string.intro),style=MaterialTheme.typography.bodyLarge)
                if(p==null) BigButton(s(R.string.choose_place),Icons.Default.LocationOn,choose)
                else {
                    if(b!=null) WeatherCard(b)
                    suggestionIds.forEach { id->val prompt=s(id)
                        OutlinedButton(onClick={vm.send(prompt)},enabled=!busy,modifier=Modifier.fillMaxWidth().heightIn(min=56.dp),shape=RoundedCornerShape(16.dp)) { Text(prompt,style=MaterialTheme.typography.bodyLarge) }
                    }
                }
            } }
        }
        if(p!=null) Surface(tonalElevation=2.dp) { Column(Modifier.padding(horizontal=16.dp,vertical=12.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(value=draft,onValueChange={draft=it.take(1000)},label={Text(s(R.string.type_question))},modifier=Modifier.fillMaxWidth(),maxLines=4,shape=RoundedCornerShape(16.dp))
            Row(horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick={
                    try { launcher.launch(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                        putExtra(RecognizerIntent.EXTRA_LANGUAGE,vm.value("language","en"))
                        putExtra(RecognizerIntent.EXTRA_PROMPT,context.getString(R.string.type_question))
                    }) } catch(e:android.content.ActivityNotFoundException) { Toast.makeText(context,unavailable,Toast.LENGTH_LONG).show() }
                },modifier=Modifier.weight(1f).heightIn(min=56.dp),enabled=!busy) { Icon(Icons.Default.Mic,null);Spacer(Modifier.width(8.dp));Text(s(R.string.speak)) }
                Button(onClick={vm.send(draft);draft=""},modifier=Modifier.weight(1f).heightIn(min=56.dp),enabled=draft.isNotBlank()&&!busy) { Text(s(R.string.send));Spacer(Modifier.width(8.dp));Icon(Icons.AutoMirrored.Filled.Send,null) }
            }
        } }
    }
}
@Composable fun WeatherCard(b:BundleDto) {
    val now=Instant.now()
    var details by rememberSaveable(b.retrieved_at) { mutableStateOf(false) }
    val hour=b.hourly.minByOrNull{kotlin.math.abs(Instant.parse(it.time).epochSecond-now.epochSecond)}
    val age=Duration.between(Instant.parse(b.retrieved_at),now).toMinutes().coerceAtLeast(0)
    Surface(color=MaterialTheme.colorScheme.primaryContainer,shape=RoundedCornerShape(24.dp),modifier=Modifier.fillMaxWidth()) {
        Column(Modifier.padding(22.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            Text(s(R.string.saved_weather),style=MaterialTheme.typography.titleMedium)
            if(hour?.temperature!=null) Text("${hour.temperature}°C",style=MaterialTheme.typography.displayMedium,fontWeight=FontWeight.Bold)
            conditionResource(hour?.weather_code?.toInt())?.let{Text(s(it),style=MaterialTheme.typography.titleLarge)}
            if(hour?.apparent_temperature!=null) Text("${s(R.string.feels_like)} ${hour.apparent_temperature}°C")
            Text("${s(R.string.updated)} $age ${s(R.string.minutes_ago)}",style=MaterialTheme.typography.bodyMedium)
            if(Freshness.weather(b.retrieved_at)!=FreshnessState.FRESH) Text(s(R.string.saved_notice))
            OutlinedButton(onClick={details=!details},modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)) {
                Icon(if(details) Icons.Default.ExpandLess else Icons.Default.ExpandMore,null)
                Spacer(Modifier.width(8.dp));Text(s(if(details) R.string.hide_details else R.string.show_details))
            }
            if(details) {
                if(hour?.rain_chance!=null) Text("${s(R.string.rain)}: ${hour.rain_chance}%")
                if(hour?.wind_ms!=null) Text("${s(R.string.wind)}: ${String.format(Locale.getDefault(),"%.0f km/h",hour.wind_ms*3.6)}")
                if(hour?.humidity!=null) Text("${s(R.string.humidity)}: ${hour.humidity}%")
                Text("${s(R.string.sources)}: ${b.sources.joinToString()}",style=MaterialTheme.typography.bodyMedium)
                if(b.source_count==1) Text(s(R.string.single_source),style=MaterialTheme.typography.bodyMedium)
                if(b.agreement=="sources_disagree") Text(s(R.string.disagree))
                b.confidence?.let { confidence ->
                    Text("${s(R.string.forecast_confidence)}: ${confidence.score}/100 · ${confidence.label}",fontWeight=FontWeight.Bold)
                    confidence.reasons.forEach { Text("• $it",style=MaterialTheme.typography.bodyMedium) }
                    Text(s(R.string.confidence_help),style=MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}
@Composable fun ForecastScreen(b:BundleDto?,busy:Boolean,refresh:()->Unit,choose:()->Unit) {
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp),modifier=Modifier.fillMaxSize()) {
        item { Heading(s(R.string.forecast)) }
        if(b==null) item { Text(s(R.string.no_saved));Spacer(Modifier.height(16.dp));BigButton(s(R.string.choose_place),Icons.Default.LocationOn,choose);BigButton(s(R.string.download),Icons.Default.Download,refresh,!busy) }
        else {
            item { WeatherCard(b);Spacer(Modifier.height(16.dp));BigButton(s(R.string.download),Icons.Default.Download,refresh,!busy) }
            item { Text(s(R.string.forecast_help)) }
            b.daily.orEmpty().forEach { day -> item {
                Surface(color=MaterialTheme.colorScheme.surfaceVariant,shape=RoundedCornerShape(20.dp),modifier=Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(6.dp)) {
                        Text(day.date,fontWeight=FontWeight.Bold,style=MaterialTheme.typography.titleMedium)
                        Text("${s(R.string.temperature)}: ${day.temperature_min?.let{"$it°C"}?:s(R.string.unavailable)} – ${day.temperature_max?.let{"$it°C"}?:s(R.string.unavailable)}")
                        Text("${s(R.string.rain)}: ${day.rain_chance_max?.let{"$it%"}?:s(R.string.unavailable)}")
                    }
                }
            } }
            item { Text(s(R.string.hourly),style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold) }
            items(b.hourly.filter{Instant.parse(it.time)>Instant.now().minusSeconds(3600)}.take(72)) { h ->
                OutlinedCard(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(6.dp)) {
                    Text(Instant.parse(h.time).atZone(ZoneId.of(b.location.timezone)).format(DateTimeFormatter.ofPattern("EEE d MMM · h a")),fontWeight=FontWeight.Bold)
                    Text("${s(R.string.temperature)}: ${h.temperature?.let{"$it°C"}?:s(R.string.unavailable)}")
                    Text("${s(R.string.rain)}: ${h.rain_chance?.let{"$it%"}?:s(R.string.unavailable)}")
                    Text("${s(R.string.wind)}: ${h.wind_ms?.let{String.format(Locale.getDefault(),"%.0f km/h",it*3.6)}?:s(R.string.unavailable)}")
                    if(h.wind_gust_ms!=null) Text("${s(R.string.gusts)}: ${String.format(Locale.getDefault(),"%.0f km/h",h.wind_gust_ms*3.6)}")
                    if(h.visibility_m!=null) Text("${s(R.string.visibility)}: ${String.format(Locale.getDefault(),"%.1f km",h.visibility_m/1000)}")
                    if(h.uv_index!=null) Text("${s(R.string.uv)}: ${h.uv_index}")
                } }
            }
            item { Text("${s(R.string.sources)}: ${b.sources.joinToString()}",style=MaterialTheme.typography.bodyMedium) }
        }
    }
}
@Composable fun AlertScreen(bundle:BundleDto?) {
    val context=LocalContext.current
    val official=bundle?.official_alerts.orEmpty().filter { alert->bundle!=null && Freshness.officialAlert(bundle.retrieved_at,alert.expires)!=FreshnessState.STALE }
    val expiredCount=bundle?.official_alerts.orEmpty().size-official.size
    Column(Modifier.verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(20.dp)) {
        Heading(s(R.string.alerts))
        if(official.isNotEmpty()) official.forEach { OfficialAlertCard(it) } else {
            Icon(Icons.Default.Info,null,Modifier.size(48.dp),tint=MaterialTheme.colorScheme.primary)
            Text(s(R.string.alert_unknown),style=MaterialTheme.typography.titleLarge)
            Text(s(R.string.alert_help))
        }
        if(expiredCount>0) Text(s(R.string.expired_hidden),style=MaterialTheme.typography.bodyMedium)
        Text(s(R.string.offline_alerts))
        BigButton(s(R.string.open_imd),Icons.AutoMirrored.Filled.OpenInNew,{
            context.startActivity(Intent(Intent.ACTION_VIEW,android.net.Uri.parse("https://mausam.imd.gov.in/")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        })
        HorizontalDivider()
        Heading(s(R.string.risk_estimates))
        Text(s(R.string.risk_help))
        if(bundle?.risk_estimates.isNullOrEmpty()) Text(s(R.string.no_risk_estimates))
        bundle?.risk_estimates.orEmpty().forEach { risk ->
            OutlinedCard(Modifier.fillMaxWidth()) { Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment=Alignment.CenterVertically) { Icon(Icons.Default.Warning,null,tint=MaterialTheme.colorScheme.error);Spacer(Modifier.width(8.dp));Text(s(R.string.weather_risk),fontWeight=FontWeight.Bold) }
                Text(risk.message,style=MaterialTheme.typography.titleMedium)
                Text(risk.rationale)
                Text(risk.disclaimer,style=MaterialTheme.typography.bodyMedium)
            } }
        }
    }
}
@Composable fun OfficialAlertCard(alert:OfficialAlert) {
    val colors=when(alertLevel(alert.severity)) {
        AlertLevel.RED -> MaterialTheme.colorScheme.errorContainer to MaterialTheme.colorScheme.onErrorContainer
        AlertLevel.ORANGE -> MaterialTheme.colorScheme.tertiaryContainer to MaterialTheme.colorScheme.onTertiaryContainer
        AlertLevel.YELLOW -> MaterialTheme.colorScheme.secondaryContainer to MaterialTheme.colorScheme.onSecondaryContainer
    }
    Surface(color=colors.first,contentColor=colors.second,shape=RoundedCornerShape(20.dp),modifier=Modifier.fillMaxWidth().semantics{liveRegion=LiveRegionMode.Assertive}) {
        Column(Modifier.padding(20.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically) { Icon(Icons.Default.Warning,null);Spacer(Modifier.width(8.dp));Text(s(R.string.official_warning),fontWeight=FontWeight.Bold) }
            Text(alert.headline,style=MaterialTheme.typography.titleLarge,fontWeight=FontWeight.Bold)
            alert.description?.let{Text(it)}
            alert.instruction?.let{Text(it,fontWeight=FontWeight.Bold)}
            Text("${alert.severity.replaceFirstChar{it.uppercase()}} · ${alert.certainty.replaceFirstChar{it.uppercase()}}")
            alert.expires?.let{Text("${s(R.string.expires)}: $it",style=MaterialTheme.typography.bodyMedium)}
        }
    }
}
@Composable fun PlaceDialog(vm:WeatherViewModel,onDismiss:()->Unit,onChoose:(Place)->Unit) {
    var query by rememberSaveable{mutableStateOf("")}
    val results by vm.results.collectAsState()
    val saved by vm.savedPlaces.collectAsState()
    val busy by vm.searchBusy.collectAsState()
    val context=LocalContext.current
    val locationUnavailable=s(R.string.location_unavailable)
    fun chooseLastLocation() {
        if(ContextCompat.checkSelfPermission(context,android.Manifest.permission.ACCESS_COARSE_LOCATION)!=PackageManager.PERMISSION_GRANTED) return
        val manager=context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val location=runCatching { manager.getProviders(true).mapNotNull { provider->runCatching { manager.getLastKnownLocation(provider) }.getOrNull() }.maxByOrNull { it.time } }.getOrNull()
        if(location==null) Toast.makeText(context,locationUnavailable,Toast.LENGTH_LONG).show()
        else vm.resolveCurrentLocation(location.latitude,location.longitude,context.getString(R.string.current_location),onChoose)
    }
    val locationPermission=rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants->
        if(grants.values.any { it }) chooseLastLocation() else Toast.makeText(context,locationUnavailable,Toast.LENGTH_LONG).show()
    }
    AlertDialog(onDismissRequest=onDismiss,title={Text(s(R.string.choose_place))},text={
        Column(Modifier.heightIn(max=440.dp).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(12.dp)) {
            Text(s(R.string.place_help))
            BigButton(s(R.string.use_current_location),Icons.Default.MyLocation,{
                if(ContextCompat.checkSelfPermission(context,android.Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED) chooseLastLocation()
                else locationPermission.launch(arrayOf(android.Manifest.permission.ACCESS_COARSE_LOCATION,android.Manifest.permission.ACCESS_FINE_LOCATION))
            })
            Text(s(R.string.location_optional),style=MaterialTheme.typography.bodyMedium)
            if(saved.isNotEmpty()) {
                Text(s(R.string.saved_places),style=MaterialTheme.typography.titleMedium)
                saved.forEach { savedPlace->OutlinedButton(onClick={onChoose(savedPlace.place())},modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)) { Text(savedPlace.label) } }
                HorizontalDivider()
            }
            OutlinedTextField(query,{query=it},label={Text(s(R.string.city_village))},modifier=Modifier.fillMaxWidth(),singleLine=true)
            BigButton(s(R.string.search),Icons.Default.Search,{vm.search(query)},query.trim().length>=2&&!busy)
            if(busy) CircularProgressIndicator()
            results.forEach { place->OutlinedButton(onClick={onChoose(place)},modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)) { Text(place.name) } }
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
    val notificationPermission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted->vm.save("risk_notifications",granted.toString()) }
    val officialNotificationPermission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted->vm.save("official_notifications",granted.toString()) }
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
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(14.dp),modifier=Modifier.fillMaxSize()) {
        item { Heading(s(R.string.settings));Text(s(R.string.settings_intro)) }
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
        item { Row(Modifier.fillMaxWidth().heightIn(min=56.dp).toggleable(value=preference("risk_notifications")=="true",onValueChange={enabled->
            if(enabled && android.os.Build.VERSION.SDK_INT>=33) notificationPermission.launch(android.Manifest.permission.POST_NOTIFICATIONS) else vm.save("risk_notifications",enabled.toString())
        }),verticalAlignment=Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text(s(R.string.risk_notifications));Text(s(R.string.risk_notification_help),style=MaterialTheme.typography.bodyMedium) }
            Switch(checked=preference("risk_notifications")=="true",onCheckedChange=null)
        } }
        item { Row(Modifier.fillMaxWidth().heightIn(min=56.dp).toggleable(value=preference("official_notifications")=="true",onValueChange={enabled->
            if(enabled && android.os.Build.VERSION.SDK_INT>=33) officialNotificationPermission.launch(android.Manifest.permission.POST_NOTIFICATIONS) else vm.save("official_notifications",enabled.toString())
        }),verticalAlignment=Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text(s(R.string.official_notifications));Text(s(R.string.official_notification_help),style=MaterialTheme.typography.bodyMedium) }
            Switch(checked=preference("official_notifications")=="true",onCheckedChange=null)
        } }
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
                    Text("${summary.messageCount} messages",style=MaterialTheme.typography.bodyMedium)
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick={vm.openConversation(summary.conversationId);onOpenChat()},modifier=Modifier.weight(1f).heightIn(min=52.dp)){Text(s(R.string.continue_chat))}
                        OutlinedButton(onClick={deleteConversationId=summary.conversationId},modifier=Modifier.weight(1f).heightIn(min=52.dp)){Text(s(R.string.delete))}
                    }
                }
            }
        }
        item { OutlinedButton(onClick={vm.startNewChat();onOpenChat()},modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)){Text(s(R.string.new_chat))} }
        item { OutlinedButton(onClick={confirm=true},modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)){Text(s(R.string.clear_data))} }
        item { TextButton(onClick={advanced=!advanced},modifier=Modifier.heightIn(min=52.dp)){Text(s(R.string.connection_settings))}
            if(advanced) {
                Text(s(R.string.server_help))
                OutlinedTextField(server,{server=it},label={Text("Server URL")},modifier=Modifier.fillMaxWidth())
                val valid=runCatching{val uri=java.net.URI(server);uri.host!=null && (uri.scheme=="https" || BuildConfig.DEBUG && uri.scheme=="http") && uri.userInfo==null && server.endsWith("/")}.getOrDefault(false)
                Button(onClick={vm.save("server",server.trim())},enabled=valid){Text(s(R.string.save))}
            }
        }
    }
}
@Composable fun Choice(label:String,selected:Boolean,onClick:()->Unit) {
    OutlinedCard(onClick=onClick,modifier=Modifier.fillMaxWidth().heightIn(min=56.dp).semantics{this.selected=selected}) {
        Row(Modifier.padding(horizontal=16.dp,vertical=12.dp),verticalAlignment=Alignment.CenterVertically) {
            RadioButton(selected=selected,onClick=null);Spacer(Modifier.width(12.dp));Text(label,style=MaterialTheme.typography.bodyLarge)
        }
    }
}








