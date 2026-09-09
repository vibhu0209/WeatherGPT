package `in`.weathergpt

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.datastore.preferences.core.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

class WeatherViewModel(app:Application):AndroidViewModel(app) {
    val repo=Repository(app)
    private val settings=app.settings
    val preferences=settings.data.stateIn(viewModelScope,SharingStarted.Eagerly,emptyPreferences())
    val conversations=repo.dao.conversations().stateIn(viewModelScope,SharingStarted.WhileSubscribed(5000),emptyList())
    @OptIn(ExperimentalCoroutinesApi::class)
    val messages=preferences.map { it[stringPreferencesKey("conversation_id")] ?: "" }.distinctUntilChanged().flatMapLatest { id ->
        if(id.isBlank()) repo.dao.messages() else repo.dao.messagesFor(id)
    }.stateIn(viewModelScope,SharingStarted.WhileSubscribed(5000),emptyList())
    val savedPlaces=repo.dao.savedPlaces().stateIn(viewModelScope,SharingStarted.WhileSubscribed(5000),emptyList())
    val busy=MutableStateFlow(false)
    val offline=MutableStateFlow(false)
    val error=MutableStateFlow("")
    val results=MutableStateFlow<List<Place>>(emptyList())
    val searchBusy=MutableStateFlow(false)
    val chatStatus=MutableStateFlow("")
    var dayOffset:Int
        get()=value("day_offset","0").toIntOrNull()?:0
        set(day){save("day_offset",day.toString())}
    val place=preferences.map { p->p[stringPreferencesKey("place")]?.let{runCatching{repo.gson.fromJson(it,Place::class.java)}.getOrNull()} }.distinctUntilChanged().stateIn(viewModelScope,SharingStarted.Eagerly,null)
    @OptIn(ExperimentalCoroutinesApi::class)
    val weather=place.flatMapLatest { p->if(p==null) flowOf(null) else repo.dao.weather(repo.key(p)).map { it?.let{runCatching{repo.gson.fromJson(it.json,BundleDto::class.java)}.getOrNull()} } }.stateIn(viewModelScope,SharingStarted.Eagerly,null)
    fun value(key:String,default:String="")=preferences.value[stringPreferencesKey(key)]?:default
    fun save(key:String,value:String) { viewModelScope.launch { settings.edit{it[stringPreferencesKey(key)]=value}; if(key=="wifi") ForecastSync.schedule(getApplication(),value=="true") } }
    fun choose(p:Place) { viewModelScope.launch { androidx.work.WorkManager.getInstance(getApplication()).cancelAllWorkByTag("official-alerts"); repo.dao.savePlace(SavedPlace(repo.key(p),p.name,p.name,p.latitude,p.longitude,p.timezone)); settings.edit{it[stringPreferencesKey("place")]=repo.gson.toJson(p)}; dayOffset=0; results.value=emptyList(); ForecastSync.schedule(getApplication(),value("wifi","true")=="true"); refresh(p) } }
    private var searchJob:Job?=null
    fun search(q:String) {
        if(q.trim().length<2) return
        searchJob?.cancel()
        searchJob=viewModelScope.launch {
            searchBusy.value=true; error.value=""; results.value=emptyList()
            try { results.value=repo.api(base()).search(q.trim(),value("language","en")).locations; if(results.value.isEmpty()) error.value="no_places" }
            catch(e:CancellationException) { throw e }
            catch(e:Exception) { android.util.Log.w("WeatherGPT","place_search_failed type=${e.javaClass.simpleName}"); error.value="search_failed" }
            finally { searchBusy.value=false }
        }
    }
    fun resolveCurrentLocation(latitude:Double,longitude:Double,name:String,onResolved:(Place)->Unit) {
        viewModelScope.launch {
            searchBusy.value=true; error.value=""
            try { onResolved(repo.api(base()).resolve(latitude,longitude,name).location) }
            catch(e:CancellationException) { throw e }
            catch(e:Exception) { android.util.Log.w("WeatherGPT","location_resolve_failed type=${e.javaClass.simpleName}"); error.value="location_failed" }
            finally { searchBusy.value=false }
        }
    }
    private fun base()=value("server",BuildConfig.API_URL)
    fun refresh(p:Place?=place.value) {
        if(p==null || busy.value) return
        viewModelScope.launch {
            busy.value=true; error.value=""
            try { repo.refresh(p,base()); repo.dao.weatherOnce(repo.key(p))?.let { scheduleCachedAlerts(getApplication(),p,repo.gson.fromJson(it.json,BundleDto::class.java)) }; offline.value=false }
            catch(e:CancellationException) { throw e }
            catch(e:Exception) { offline.value=true; error.value="refresh_failed" }
            finally { busy.value=false }
        }
    }
    fun send(text:String) {
        val p=place.value?:return
        if(text.isBlank() || busy.value) return
        viewModelScope.launch {
            busy.value=true; error.value=""; chatStatus.value="sending"
            val lang=value("language","en")
            val conversation=value("conversation_id").ifBlank { java.util.UUID.randomUUID().toString().also{save("conversation_id",it)} }
            val contextTimestamp=repo.dao.weatherOnce(repo.key(p))?.let { repo.gson.fromJson(it.json,BundleDto::class.java).retrieved_at }
            repo.dao.message(Message(role="user",text=text.trim(),language=lang,conversationId=conversation,resolvedLocationId=repo.key(p),weatherContextTimestamp=contextTimestamp))
            chatStatus.value="checking"
            try {
                val a=repo.api(base()).chat(ChatBody(text.trim(),p,lang,value("profile","general"),dayOffset,conversation))
                if(a.sources.isEmpty() && repo.dao.weatherOnce(repo.key(p))!=null) throw java.io.IOException("Live sources unavailable")
                dayOffset=a.day_offset
                val downloaded=java.time.Instant.parse(a.retrieved_at).atZone(java.time.ZoneId.of(p.timezone)).format(java.time.format.DateTimeFormatter.ofPattern("d MMM, h:mm a",java.util.Locale.forLanguageTag(a.language)))
                val sourceLabel=if(a.language=="hi") "डाउनलोड किया: " else "Downloaded: "
                repo.dao.message(Message(role="assistant",text=a.answer+"\n\n"+sourceLabel+downloaded+" · "+a.sources.joinToString(),language=a.language,conversationId=conversation,resolvedLocationId=repo.key(p),weatherContextTimestamp=a.retrieved_at))
                offline.value=false
            } catch(e:CancellationException) { throw e }
            catch(e:Exception) {
                offline.value=true
                val cached=repo.dao.weatherOnce(repo.key(p))?.let{repo.gson.fromJson(it.json,BundleDto::class.java)}
                val (message,day)=Offline.answer(text,cached,dayOffset,lang); dayOffset=day
                repo.dao.message(Message(role="assistant",text=message,language=if(lang=="hi") "hi" else "en",conversationId=conversation,resolvedLocationId=repo.key(p),weatherContextTimestamp=cached?.retrieved_at))
            } finally { busy.value=false; chatStatus.value="" }
        }
    }
    fun clearChat() { viewModelScope.launch{settings.edit{it.remove(stringPreferencesKey("conversation_id"));it[stringPreferencesKey("day_offset")]="0"}} }
    fun startNewChat() { viewModelScope.launch { settings.edit { it.remove(stringPreferencesKey("conversation_id")); it[stringPreferencesKey("day_offset")]="0" } } }
    fun openConversation(conversationId:String) { save("conversation_id", conversationId) }
    fun deleteConversation(conversationId:String) {
        viewModelScope.launch {
            repo.dao.deleteConversation(conversationId)
            if(value("conversation_id")==conversationId) settings.edit { it.remove(stringPreferencesKey("conversation_id")); it[stringPreferencesKey("day_offset")]="0" }
        }
    }
    fun clearAll() { viewModelScope.launch { androidx.work.WorkManager.getInstance(getApplication()).cancelAllWork(); androidx.core.app.NotificationManagerCompat.from(getApplication()).cancelAll(); repo.dao.clearChat(); repo.dao.clearWeather(); repo.dao.clearPlaces(); settings.edit{it.clear()}; dayOffset=0 } }
}








