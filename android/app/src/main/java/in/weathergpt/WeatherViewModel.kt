package `in`.weathergpt

import android.app.Application
import android.content.res.Configuration
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.datastore.preferences.core.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import java.util.Locale

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
    val followUps=MutableStateFlow<List<String>>(emptyList())
    val backendOnline=MutableStateFlow<Boolean?>(null)
    /**
     * Failure for the weather-bundle / health path only.
     * Chat offline fallback must not sticky-overwrite this, or Home keeps a
     * connection banner after Room already has a valid forecast.
     */
    val failure=MutableStateFlow(NetFailure.NONE)
    private fun online()=hasNetwork(getApplication())
    private fun recordWeather(operation:String,path:String,error:Throwable?) {
        val kind=if(error==null) NetFailure.NONE else classifyFailure(error,online())
        failure.value=kind
        offline.value=kind==NetFailure.NO_NETWORK || kind==NetFailure.SERVER_UNREACHABLE || kind==NetFailure.TIMEOUT
        backendOnline.value=when(kind) {
            NetFailure.NONE,NetFailure.PROVIDER_UNAVAILABLE,NetFailure.SERVER_ERROR,NetFailure.BAD_RESPONSE,NetFailure.AUTH_CONFIGURATION_ERROR->true
            NetFailure.NO_NETWORK,NetFailure.SERVER_UNREACHABLE,NetFailure.TIMEOUT->false
        }
        if(backendOnline.value==true) markConnected()
        NetLog.call(operation,base(),path,(error as? BackendHttpException)?.code,kind,error)
    }
    private fun recordChat(operation:String,path:String,error:Throwable?) {
        // Chat outcomes are logged but do not drive the weather status banner.
        val kind=if(error==null) NetFailure.NONE else classifyFailure(error,online())
        if(error==null) {
            offline.value=false
            backendOnline.value=true
            markConnected()
            // A live chat round-trip proves the backend is reachable; clear a sticky weather transport error.
            if(failure.value==NetFailure.SERVER_UNREACHABLE || failure.value==NetFailure.TIMEOUT || failure.value==NetFailure.NO_NETWORK) {
                failure.value=NetFailure.NONE
            }
        }
        NetLog.call(operation,base(),path,(error as? BackendHttpException)?.code,kind,error)
    }
    private fun markConnected() { save("last_connected",System.currentTimeMillis().toString()) }
    var dayOffset:Int
        get()=value("day_offset","0").toIntOrNull()?:0
        set(day){save("day_offset",day.toString())}
    val place=preferences.map { p->p[stringPreferencesKey("place")]?.let{runCatching{repo.gson.fromJson(it,Place::class.java)}.getOrNull()} }.distinctUntilChanged().stateIn(viewModelScope,SharingStarted.Eagerly,null)
    @OptIn(ExperimentalCoroutinesApi::class)
    val weather=place.flatMapLatest { p->
        if(p==null) flowOf<BundleDto?>(null)
        else flow<BundleDto?> {
            val key=repo.key(p)
            repo.ensureWeatherKey(p)
            repo.dao.weather(key).collect { saved ->
                val bundle=saved?.let{runCatching{repo.gson.fromJson(it.json,BundleDto::class.java)}.getOrNull()}
                CacheLog.emit(bundle!=null, key)
                emit(bundle)
            }
        }
    }.stateIn(viewModelScope,SharingStarted.Eagerly,null)
    fun value(key:String,default:String="")=preferences.value[stringPreferencesKey(key)]?:default
    fun save(key:String,value:String) { viewModelScope.launch {
        settings.edit{it[stringPreferencesKey(key)]=value}
        if(key=="server") repo.workingBase=null
        if(key=="wifi" || key=="low_data") ForecastSync.schedule(getApplication(),if(key=="wifi") value=="true" else this@WeatherViewModel.value("wifi","true")=="true",if(key=="low_data") value=="true" else this@WeatherViewModel.value("low_data")=="true")
    } }
    val comparePlace=MutableStateFlow<Place?>(null)
    fun setComparePlace(place:Place?) { comparePlace.value=place }
    fun choose(p:Place,purpose:String="home") { viewModelScope.launch {
        androidx.work.WorkManager.getInstance(getApplication()).cancelAllWorkByTag("official-alerts")
        val profile=purposeToProfile(purpose)
        val stable=normalizePlace(p)
        repo.dao.savePlace(SavedPlace(repo.key(stable),stable.name,stable.name,stable.latitude,stable.longitude,stable.timezone,purpose))
        settings.edit {
            it[stringPreferencesKey("place")]=repo.gson.toJson(stable)
            it[stringPreferencesKey("profile")]=profile
            it[stringPreferencesKey("place_purpose")]=purpose
            it[stringPreferencesKey("onboarded")]="true"
        }
        dayOffset=0; results.value=emptyList(); comparePlace.value=null
        ForecastSync.schedule(getApplication(),value("wifi","true")=="true",value("low_data")=="true"); refresh(stable)
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
    fun schedulePlaceSearch(q:String) {
        search(q, debounceMs=PLACE_SEARCH_DEBOUNCE_MS)
    }
    fun search(q:String, debounceMs:Long=0L) {
        val trimmed=q.trim()
        if(trimmed.length<PLACE_SEARCH_MIN_CHARS) {
            searchJob?.cancel()
            results.value=emptyList()
            if(error.value=="no_places" || error.value=="search_failed") error.value=""
            return
        }
        if(placeSearchUnavailableOffline(online())) {
            searchJob?.cancel()
            results.value=emptyList()
            error.value="search_failed"
            searchBusy.value=false
            return
        }
        searchJob?.cancel()
        searchJob=viewModelScope.launch {
            if(debounceMs>0) delay(debounceMs)
            if(!isActive) return@launch
            if(!shouldRunPlaceSearch(trimmed, online())) return@launch
            searchBusy.value=true; error.value=""; results.value=emptyList()
            try { results.value=repo.call(base()){it.search(trimmed,value("language","en"))}.locations; if(results.value.isEmpty()) error.value="no_places" }
            catch(e:CancellationException) { throw e }
            catch(e:Exception) { NetLog.call("search",base(),"v1/locations/search",null,classifyFailure(e,online()),e); error.value="search_failed" }
            finally { searchBusy.value=false }
        }
    }
    fun resolveCurrentLocation(latitude:Double,longitude:Double,name:String,onResolved:(Place)->Unit,onFailed:(()->Unit)?=null) {
        viewModelScope.launch {
            searchBusy.value=true; error.value=""
            try { onResolved(repo.call(base()){it.resolve(ResolveBody(latitude,longitude,name))}.location) }
            catch(e:CancellationException) { throw e }
            catch(e:Exception) { NetLog.call("resolve",base(),"v1/locations/resolve",null,classifyFailure(e,online()),e); error.value="location_failed"; onFailed?.invoke() }
            finally { searchBusy.value=false }
        }
    }
    /** The effective backend address: the Settings override if set, otherwise the build default. */
    fun base()=repo.workingBase ?: normalizeBaseUrl(value("server"),BuildConfig.API_URL)
    /** Real reachability probe: the same Retrofit client the rest of the app uses, against GET /health. */
    fun checkBackend() {
        viewModelScope.launch {
            try {
                val status=repo.call(base()){it.health()}["status"]?.toString()
                if(status=="ok") { backendOnline.value=true; failure.value=NetFailure.NONE; offline.value=false; markConnected()
                    NetLog.call("health",base(),"health",200,NetFailure.NONE) }
                else {
                    backendOnline.value=false
                    failure.value=NetFailure.BAD_RESPONSE
                    NetLog.call("health",base(),"health",200,NetFailure.BAD_RESPONSE)
                }
            } catch(e:CancellationException) { throw e }
            catch(e:Exception) {
                val kind=classifyFailure(e,online())
                backendOnline.value=false
                if(failure.value==NetFailure.NONE) failure.value=kind
                val code=(e as? BackendHttpException)?.code ?: (e as? retrofit2.HttpException)?.code()
                NetLog.call("health",base(),"health",code,kind,e)
            }
        }
    }
    fun refresh(p:Place?=place.value) {
        if(p==null || busy.value) return
        viewModelScope.launch {
            busy.value=true; error.value=""
            try {
                // Always try Room first so offline reopen never waits on network.
                repo.ensureWeatherKey(p)
                if(!online()) {
                    val has=repo.dao.weatherOnce(repo.key(p))!=null
                    failure.value=if(has) NetFailure.NO_NETWORK else NetFailure.NO_NETWORK
                    offline.value=true
                    backendOnline.value=false
                    CacheLog.emit(has,repo.key(p))
                    return@launch
                }
                repo.refresh(p,base(),value("low_data")=="true")
                repo.dao.weatherOnce(repo.key(p))?.let { scheduleCachedAlerts(getApplication(),p,repo.gson.fromJson(it.json,BundleDto::class.java)) }
                recordWeather("bundle","v1/weather/bundle",null)
            }
            catch(e:CancellationException) { throw e }
            catch(e:Exception) {
                // Keep any Room weather; only record transport failure for the banner.
                repo.ensureWeatherKey(p)
                recordWeather("bundle","v1/weather/bundle",e)
            }
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
                val saved=savedPlaces.value.map { it.place() }
                val a=repo.call(base()){it.chat(ChatBody(text.trim(),p,lang,value("profile","general"),dayOffset,conversation,secondary,saved))}
                if(a.sources.isEmpty() && repo.dao.weatherOnce(repo.key(p))!=null) throw ProviderUnavailableException("Live sources unavailable")
                dayOffset=a.day_offset
                followUps.value=a.follow_up_suggestions?.filter { it.isNotBlank() }?.take(3) ?: emptyList()
                val downloaded=java.time.Instant.parse(a.retrieved_at).atZone(java.time.ZoneId.of(p.timezone)).format(java.time.format.DateTimeFormatter.ofPattern("d MMM, h:mm a",java.util.Locale.forLanguageTag(a.language)))
                val sourceLabel=getApplication<Application>().createConfigurationContext(
                    Configuration(getApplication<Application>().resources.configuration).apply { setLocale(Locale.forLanguageTag(lang)) }
                ).getString(R.string.downloaded_prefix)
                repo.dao.message(Message(role="assistant",text=a.answer+"\n\n"+sourceLabel+downloaded+" · "+a.sources.joinToString(),language=a.language,conversationId=conversation,resolvedLocationId=repo.key(p),weatherContextTimestamp=a.retrieved_at))
                recordChat("chat","v1/chat/message",null)
            } catch(e:CancellationException) { throw e }
            catch(e:Exception) {
                recordChat("chat","v1/chat/message",e)
                followUps.value=emptyList()
                val cached=repo.dao.weatherOnce(repo.key(p))?.let { saved ->
                    runCatching { repo.gson.fromJson(saved.json,BundleDto::class.java) }
                        .onFailure { parse -> NetLog.call("cache_parse",base(),"room/weather",null,NetFailure.BAD_RESPONSE,parse) }
                        .getOrNull()
                }
                val (message,day)=Offline.answer(text,cached,dayOffset,lang); dayOffset=day
                repo.dao.message(Message(role="assistant",text=message,language=lang,conversationId=conversation,resolvedLocationId=repo.key(p),weatherContextTimestamp=cached?.retrieved_at))
            } finally { busy.value=false; chatStatus.value="" }
        }
    }
    fun startNewChat() {
        viewModelScope.launch {
            settings.edit {
                it[stringPreferencesKey("conversation_id")]=java.util.UUID.randomUUID().toString()
                it[stringPreferencesKey("day_offset")]="0"
            }
        }
    }
    fun openConversation(conversationId:String) { save("conversation_id", conversationId) }
    fun deleteConversation(conversationId:String) {
        viewModelScope.launch {
            repo.dao.deleteConversation(conversationId)
            if(value("conversation_id")==conversationId) settings.edit { it.remove(stringPreferencesKey("conversation_id")); it[stringPreferencesKey("day_offset")]="0" }
        }
    }
    fun deletePlace(place:SavedPlace) { viewModelScope.launch {
        repo.dao.deletePlace(place.key)
        repo.dao.deleteAlertRulesForPlace(place.key)
        val current=this@WeatherViewModel.place.value
        if(current!=null && repo.key(current)==place.key) {
            settings.edit { it.remove(stringPreferencesKey("place")) }
        }
        if(comparePlace.value!=null && repo.key(comparePlace.value!!)==place.key) comparePlace.value=null
    } }
    fun sendDemoWarning() { postDemoWarning(getApplication()) }
    fun ensureDeviceRegistration() {
        viewModelScope.launch { registerDeviceIfNeeded() }
    }
    private suspend fun registerDeviceIfNeeded(): Boolean {
        if(value("device_id").isNotBlank() && value("device_token").isNotBlank()) return true
        return try {
            val registered=repo.call(base()){it.registerDevice(DeviceRegistrationBody())}
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
    fun syncAlertSubscription(enabled:Boolean,channel:String=ALERT_CHANNEL_OFFICIAL) {
        val p=place.value?:return
        viewModelScope.launch {
            val placeKey=repo.key(p)
            val id="$placeKey:$channel"
            if(enabled) repo.dao.saveAlertRule(AlertRule(id=id,placeKey=placeKey,channel=channel,enabled=true))
            else repo.dao.deleteAlertRule(id)
            if(!enabled || !registerDeviceIfNeeded()) return@launch
            val deviceId=value("device_id"); val token=value("device_token")
            if(deviceId.isBlank() || token.isBlank()) return@launch
            try {
                repo.call(base()){it.createSubscription(AlertSubscriptionBody(p.latitude,p.longitude,p.timezone,listOf(channel)),deviceId,"Bearer $token")}
            } catch(_:Exception) { android.util.Log.w("WeatherGPT","subscription_sync_failed") }
        }
    }
    fun clearAll() { viewModelScope.launch { androidx.work.WorkManager.getInstance(getApplication()).cancelAllWork(); androidx.core.app.NotificationManagerCompat.from(getApplication()).cancelAll(); repo.dao.clearChat(); repo.dao.clearWeather(); repo.dao.clearSyncMetadata(); repo.dao.clearNotificationReceipts(); repo.dao.clearPlaces(); repo.dao.clearAlertRules(); settings.edit{it.clear()}; dayOffset=0 } }
}








