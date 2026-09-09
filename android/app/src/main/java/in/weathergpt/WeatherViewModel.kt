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
    val backendOnline=MutableStateFlow<Boolean?>(null)
    var dayOffset:Int
        get()=value("day_offset","0").toIntOrNull()?:0
        set(day){save("day_offset",day.toString())}
    val place=preferences.map { p->p[stringPreferencesKey("place")]?.let{runCatching{repo.gson.fromJson(it,Place::class.java)}.getOrNull()} }.distinctUntilChanged().stateIn(viewModelScope,SharingStarted.Eagerly,null)
    @OptIn(ExperimentalCoroutinesApi::class)
    val weather=place.flatMapLatest { p->if(p==null) flowOf(null) else repo.dao.weather(repo.key(p)).map { it?.let{runCatching{repo.gson.fromJson(it.json,BundleDto::class.java)}.getOrNull()} } }.stateIn(viewModelScope,SharingStarted.Eagerly,null)
    fun value(key:String,default:String="")=preferences.value[stringPreferencesKey(key)]?:default
    fun save(key:String,value:String) { viewModelScope.launch {
        settings.edit{it[stringPreferencesKey(key)]=value}
        if(key=="wifi" || key=="low_data") ForecastSync.schedule(getApplication(),if(key=="wifi") value=="true" else this@WeatherViewModel.value("wifi","true")=="true",if(key=="low_data") value=="true" else this@WeatherViewModel.value("low_data")=="true")
    } }
    val comparePlace=MutableStateFlow<Place?>(null)
    fun setComparePlace(place:Place?) { comparePlace.value=place }
    fun choose(p:Place,purpose:String="home") { viewModelScope.launch {
        androidx.work.WorkManager.getInstance(getApplication()).cancelAllWorkByTag("official-alerts")
        val profile=purposeToProfile(purpose)
        repo.dao.savePlace(SavedPlace(repo.key(p),p.name,p.name,p.latitude,p.longitude,p.timezone,purpose))
        settings.edit {
            it[stringPreferencesKey("place")]=repo.gson.toJson(p)
            it[stringPreferencesKey("profile")]=profile
            it[stringPreferencesKey("place_purpose")]=purpose
        }
        dayOffset=0; results.value=emptyList(); comparePlace.value=null
        ForecastSync.schedule(getApplication(),value("wifi","true")=="true",value("low_data")=="true"); refresh(p)
    } }
    fun updatePlacePurpose(place:SavedPlace,purpose:String) { viewModelScope.launch {
        repo.dao.savePlace(place.copy(purpose=purpose))
        val current=this@WeatherViewModel.place.value
        if(current!=null && repo.key(current)==place.key) {
            settings.edit {
                it[stringPreferencesKey("profile")]=purposeToProfile(purpose)
                it[stringPreferencesKey("place_purpose")]=purpose
            }
        }
    } }
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
    fun resolveCurrentLocation(latitude:Double,longitude:Double,name:String,onResolved:(Place)->Unit,onFailed:(()->Unit)?=null) {
        viewModelScope.launch {
            searchBusy.value=true; error.value=""
            try { onResolved(repo.api(base()).resolve(ResolveBody(latitude,longitude,name)).location) }
            catch(e:CancellationException) { throw e }
            catch(e:Exception) { android.util.Log.w("WeatherGPT","location_resolve_failed type=${e.javaClass.simpleName}"); error.value="location_failed"; onFailed?.invoke() }
            finally { searchBusy.value=false }
        }
    }
    private fun base()=value("server",BuildConfig.API_URL)
    fun checkBackend() {
        viewModelScope.launch {
            try {
                val status=repo.api(base()).health()["status"]?.toString()
                backendOnline.value = status == "ok"
                if(status == "ok") offline.value=false
            } catch(_:Exception) {
                backendOnline.value = false
            }
        }
    }
    init { checkBackend() }
    fun refresh(p:Place?=place.value) {
        if(p==null || busy.value) return
        viewModelScope.launch {
            busy.value=true; error.value=""
            try { repo.refresh(p,base(),value("low_data")=="true"); repo.dao.weatherOnce(repo.key(p))?.let { scheduleCachedAlerts(getApplication(),p,repo.gson.fromJson(it.json,BundleDto::class.java)) }; offline.value=false }
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
                val secondary=comparePlace.value?.takeIf { repo.key(it)!=repo.key(p) }
                val a=repo.api(base()).chat(ChatBody(text.trim(),p,lang,value("profile","general"),dayOffset,conversation,secondary))
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
                repo.dao.message(Message(role="assistant",text=message,language=lang,conversationId=conversation,resolvedLocationId=repo.key(p),weatherContextTimestamp=cached?.retrieved_at))
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
    fun deletePlace(place:SavedPlace) { viewModelScope.launch { repo.dao.deletePlace(place.key) } }
    fun ensureDeviceRegistration() {
        viewModelScope.launch { registerDeviceIfNeeded() }
    }
    private suspend fun registerDeviceIfNeeded(): Boolean {
        if(value("device_id").isNotBlank() && value("device_token").isNotBlank()) return true
        return try {
            val registered=repo.api(base()).registerDevice(DeviceRegistrationBody())
            settings.edit {
                it[stringPreferencesKey("device_id")]=registered.device_id
                it[stringPreferencesKey("device_token")]=registered.device_token
            }
            true
        } catch(_:Exception) {
            android.util.Log.w("WeatherGPT","device_register_failed")
            false
        }
    }
    fun syncAlertSubscription(enabled:Boolean) {
        val p=place.value?:return
        viewModelScope.launch {
            if(!enabled || !registerDeviceIfNeeded()) return@launch
            val deviceId=value("device_id"); val token=value("device_token")
            if(deviceId.isBlank() || token.isBlank()) return@launch
            val channels=buildList {
                if(value("official_notifications")=="true") add("severe")
                if(value("risk_notifications")=="true") add("rain")
                if(isEmpty()) add("severe")
            }
            try {
                repo.api(base()).createSubscription(AlertSubscriptionBody(p.latitude,p.longitude,p.timezone,channels),deviceId,"Bearer $token")
            } catch(_:Exception) { android.util.Log.w("WeatherGPT","subscription_sync_failed") }
        }
    }
    fun clearAll() { viewModelScope.launch { androidx.work.WorkManager.getInstance(getApplication()).cancelAllWork(); androidx.core.app.NotificationManagerCompat.from(getApplication()).cancelAll(); repo.dao.clearChat(); repo.dao.clearWeather(); repo.dao.clearSyncMetadata(); repo.dao.clearNotificationReceipts(); repo.dao.clearPlaces(); settings.edit{it.clear()}; dayOffset=0 } }
}








