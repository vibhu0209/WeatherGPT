package `in`.weathergpt

import android.content.Context
import androidx.room.*
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import com.google.gson.Gson
import kotlinx.coroutines.flow.*
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.Query as HttpQuery
import retrofit2.Response
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit
import java.security.MessageDigest

val Context.settings by preferencesDataStore(name="preferences")
data class Place(val name:String, val latitude:Double, val longitude:Double, val timezone:String="Asia/Kolkata")
/** Live place search needs connectivity and at least two characters. */
fun shouldRunPlaceSearch(query:String, online:Boolean)=online && query.trim().length>=2
/** Offline place picker still offers saved/recent places; live search is unavailable. */
fun placeSearchUnavailableOffline(online:Boolean)=!online
fun placeSearchShowsEmpty(results:List<Place>, error:String)=results.isEmpty() && error=="no_places"
fun placeSearchShowsFailure(error:String)=error=="search_failed" || error=="location_failed"
fun savedPlacesRemainUsable(saved:List<SavedPlace>)=saved.isNotEmpty()
const val PLACE_SEARCH_DEBOUNCE_MS=400L
const val PLACE_SEARCH_MIN_CHARS=2

/** Built-in India cities for offline / failed live search. */
val LOCAL_PLACE_FALLBACKS = listOf(
    Place("Delhi",28.6139,77.2090),
    Place("Mumbai",19.0760,72.8777),
    Place("Bengaluru",12.9716,77.5946),
    Place("Chennai",13.0827,80.2707),
    Place("Kolkata",22.5726,88.3639),
    Place("Hyderabad",17.3850,78.4867),
    Place("Pune",18.5204,73.8567),
    Place("Ahmedabad",23.0225,72.5714),
    Place("Jaipur",26.9124,75.7873),
    Place("Lucknow",26.8467,80.9462),
    Place("Patna",25.5941,85.1376),
    Place("Bhopal",23.2599,77.4126),
    Place("Bhubaneswar",20.2961,85.8245),
    Place("Guwahati",26.1445,91.7362),
    Place("Kochi",9.9312,76.2673),
)

fun localPlaceMatches(query:String):List<Place> {
    val q=query.trim().lowercase()
    if(q.length<PLACE_SEARCH_MIN_CHARS) return emptyList()
    return LOCAL_PLACE_FALLBACKS.filter { it.name.lowercase().contains(q) }
}

/** API language codes only — never send en-IN / device tags. */
fun searchLanguageTag(raw:String):String {
    val base=raw.trim().lowercase().substringBefore('-').substringBefore('_')
    return if(base in setOf("en","hi","bn","te","mr","ta","gu","kn","ml","pa","or")) base else "en"
}

/** Stable Room key — GPS jitter must not orphan cached weather. */
fun roundCoord(value:Double):String=String.format(java.util.Locale.US,"%.4f",value)
fun placeStorageKey(latitude:Double,longitude:Double,timezone:String)=
    "${roundCoord(latitude)},${roundCoord(longitude)},$timezone"
fun samePlaceCoords(aLat:Double,aLon:Double,bLat:Double,bLon:Double)=
    roundCoord(aLat)==roundCoord(bLat) && roundCoord(aLon)==roundCoord(bLon)
fun normalizePlace(p:Place)=Place(
    p.name,
    roundCoord(p.latitude).toDouble(),
    roundCoord(p.longitude).toDouble(),
    p.timezone,
)
data class Hour(val time:String, val temperature:Double?, val rain_chance:Double?, val rain_mm:Double?, val wind_ms:Double?, val humidity:Double?, val source_count:Int=1, val apparent_temperature:Double?=null, val wind_direction:Double?=null, val wind_gust_ms:Double?=null, val visibility_m:Double?=null, val pressure_hpa:Double?=null, val cloud_cover:Double?=null, val uv_index:Double?=null, val weather_code:Double?=null)
data class Day(val date:String, val temperature_min:Double?, val temperature_max:Double?, val rain_chance_max:Double?, val rain_total_mm:Double?, val wind_max_ms:Double?, val humidity_average:Double?, val source_count:Int=0)
data class ScoreComponent(val name:String, val penalty:Int, val reason:String)
data class WeatherScore(val score:Int?, val label:String, val profile:String, val time_window:String?=null, val components:List<ScoreComponent>?=null, val limiting_factors:List<String>?=null, val calculated_at:String?=null, val disclaimer:String)
data class Recommendation(val severity:String, val message:String, val variable:String?=null, val time_window:String?=null, val rule:String?=null, val source:String?=null)
data class RiskEstimate(val id:String, val classification:String, val kind:String, val severity:String, val message:String, val valid_at:String, val supporting_value:Double, val unit:String, val rationale:String, val calculated_at:String, val disclaimer:String)
data class HazardInputs(val rain_24h_mm:Double?=null, val rain_48h_mm:Double?=null, val soil_moisture_0_to_7cm:Double?=null, val soil_moisture_7_to_28cm:Double?=null, val elevation_m:Double?=null, val slope_percent:Double?=null, val slope_note:String?=null)
data class HazardInfraItem(val name:String?=null, val `class`:String?=null, val place:String?=null, val latitude:Double?=null, val longitude:Double?=null)
data class HazardInfrastructure(val status:String?=null, val radius_m:Int?=null, val roads_at_risk_priority:List<HazardInfraItem>?=null, val settlements_nearby:List<HazardInfraItem>?=null, val message:String?=null)
data class InfrastructureHazard(val classification:String, val kind:String, val place:String, val decision:String, val severity:String, val label:String, val score:Int, val factors:List<String>?=null, val inputs:HazardInputs?=null, val infrastructure:HazardInfrastructure?=null, val disclaimer:String, val retrieved_at:String, val sources:List<String>?=null)
data class InfrastructureHazardDto(val location:Place, val data:InfrastructureHazard, val is_stale:Boolean=false)
data class OfficialAlert(val id:String, val classification:String, val sender:String?, val sent:String?, val event:String, val headline:String, val description:String?, val instruction:String?, val severity:String, val urgency:String, val certainty:String, val effective:String?, val expires:String?, val area_descriptions:List<String>?, val source_format:String, val area_match:String?=null, val area_match_uncertain:Boolean?=null)
data class Confidence(val score:Int, val label:String, val calibrated_probability:Boolean, val reasons:List<String>)
data class BundleDto(val location:Place, val hourly:List<Hour>, val retrieved_at:String, val is_stale:Boolean, val sources:List<String>, val source_count:Int, val agreement:String, val alerts_status:String, val current:Hour?=null, val daily:List<Day>?=null, val scores:Map<String,WeatherScore>?=null, val recommendations:Map<String,List<Recommendation>>?=null, val risk_estimates:List<RiskEstimate>?=null, val confidence:Confidence?=null, val disagreement_reasons:List<String>?=null, val official_status:String?=null, val official_alerts:List<OfficialAlert>?=null, val alerts_message:String?=null)
data class SearchDto(val locations:List<Place>)
data class ResolvedPlace(val location:Place)
data class ChatBody(val text:String, val location:Place, val language:String, val profile:String, val day_offset:Int, val conversation_id:String, val secondary_location:Place?=null, val saved_locations:List<Place> = emptyList())
data class AnswerDto(val answer:String, val language:String, val day_offset:Int, val retrieved_at:String, val is_stale:Boolean, val sources:List<String>, val agreement:String, val follow_up_suggestions:List<String>?=null, val response_origin:String?=null, val used_tools:List<String>?=null)
data class ResolveBody(val latitude:Double, val longitude:Double, val name:String)
data class BundleBody(val latitude:Double, val longitude:Double, val name:String, val timezone:String, val hours:Int)
data class DeviceRegistrationBody(val device_id:String?=null)
data class DeviceRegistrationDto(val device_id:String, val device_token:String, val status:String)
data class AlertSubscriptionBody(val latitude:Double, val longitude:Double, val timezone:String, val channels:List<String>)
interface Api {
    @GET("health") suspend fun health():Map<String,Any>
    @GET("v1/locations/search") suspend fun search(@HttpQuery("q") query:String,@HttpQuery("language") language:String): SearchDto
    @POST("v1/locations/resolve") suspend fun resolve(@Body body:ResolveBody):ResolvedPlace
    @POST("v1/weather/bundle") suspend fun bundle(@Body body:BundleBody,@Header("If-None-Match") etag:String?):Response<BundleDto>
    @POST("v1/chat/message") suspend fun chat(@Body body:ChatBody):AnswerDto
    @GET("v1/hazards/infrastructure") suspend fun infrastructureHazard(
        @HttpQuery("latitude") latitude:Double,
        @HttpQuery("longitude") longitude:Double,
        @HttpQuery("name") name:String,
        @HttpQuery("timezone") timezone:String,
    ):InfrastructureHazardDto
    @POST("v1/device/register") suspend fun registerDevice(@Body body:DeviceRegistrationBody=DeviceRegistrationBody()):DeviceRegistrationDto
    @POST("v1/alerts/subscriptions") suspend fun createSubscription(@Body body:AlertSubscriptionBody,@Header("X-Device-Id") deviceId:String,@Header("Authorization") authorization:String):Map<String,Any>
}
@Entity(tableName="weather") data class SavedWeather(@PrimaryKey val key:String, val json:String)
@Entity(tableName="sync_metadata") data class SyncMetadata(@PrimaryKey val key:String, val etag:String?, val lastCheckedAt:Long, val lastChangedAt:Long)
@Entity(tableName="notification_receipts") data class NotificationReceipt(@PrimaryKey val id:String, val contentSignature:String, val notifiedAt:Long)
fun canReuseNotModified(responseCode:Int,metadata:SyncMetadata?,weather:SavedWeather?)=responseCode==304 && metadata?.etag!=null && weather!=null
/** True when the server says "unchanged" but this phone has no Room body to reuse. */
fun shouldRetryUncachedNotModified(responseCode:Int,metadata:SyncMetadata?,weather:SavedWeather?)=
    responseCode==304 && weather==null
fun bundleHorizonHours(lowData:Boolean)=if(lowData)72 else 168
fun notificationContentSignature(vararg values:String?)=MessageDigest.getInstance("SHA-256").digest(values.joinToString("\u001f"){it.orEmpty()}.toByteArray()).joinToString(""){"%02x".format(it.toInt() and 0xff)}
fun shouldDeliverNotification(previous:NotificationReceipt?,signature:String)=previous?.contentSignature!=signature
const val ALERT_CHANNEL_OFFICIAL="severe"
const val ALERT_CHANNEL_RISK="rain"
fun shouldPromptForPlace(preferencesLoaded:Boolean,placeJson:String?)=preferencesLoaded && placeJson.isNullOrBlank()
fun alertRuleAllows(rules:List<AlertRule>,placeKey:String,channel:String,fallback:Boolean):Boolean {
    val rule=rules.firstOrNull { it.placeKey==placeKey && it.channel==channel }
    return rule?.enabled ?: fallback
}
fun shouldNotifyForChannel(rules:List<AlertRule>,placeKey:String,channel:String,fallback:Boolean,previous:NotificationReceipt?,signature:String):Boolean {
    return alertRuleAllows(rules,placeKey,channel,fallback) && shouldDeliverNotification(previous,signature)
}
@Entity(tableName="messages") data class Message(@PrimaryKey(autoGenerate=true) val id:Long=0, val role:String, val text:String, val language:String, val timestamp:Long=System.currentTimeMillis(), val conversationId:String="", val resolvedLocationId:String?=null, val weatherContextTimestamp:String?=null)
data class ConversationSummary(val conversationId:String, val lastTimestamp:Long, val messageCount:Int)
@Entity(tableName="saved_places") data class SavedPlace(@PrimaryKey val key:String, val label:String, val name:String, val latitude:Double, val longitude:Double, val timezone:String, val purpose:String="home") {
    fun place()=Place(name,latitude,longitude,timezone)
}
@Entity(tableName="alert_rules") data class AlertRule(@PrimaryKey val id:String, val placeKey:String, val channel:String, val enabled:Boolean=true, val updatedAt:Long=System.currentTimeMillis())
@Dao interface LocalDao {
    @Query("SELECT * FROM weather WHERE `key` = :key") fun weather(key:String):Flow<SavedWeather?>
    @Query("SELECT * FROM weather WHERE `key` = :key") suspend fun weatherOnce(key:String):SavedWeather?
    @Query("SELECT * FROM weather") suspend fun allWeather():List<SavedWeather>
    @Insert(onConflict=OnConflictStrategy.REPLACE) suspend fun save(weather:SavedWeather)
    @Query("SELECT * FROM sync_metadata WHERE `key` = :key") suspend fun syncOnce(key:String):SyncMetadata?
    @Insert(onConflict=OnConflictStrategy.REPLACE) suspend fun saveSync(metadata:SyncMetadata)
    @Transaction suspend fun saveBundle(weather:SavedWeather,metadata:SyncMetadata) { save(weather);saveSync(metadata) }
    @Query("SELECT * FROM messages ORDER BY id") fun messages():Flow<List<Message>>
    @Query("SELECT * FROM messages WHERE conversationId = :conversationId ORDER BY id") fun messagesFor(conversationId:String):Flow<List<Message>>
    @Query("SELECT conversationId, MAX(timestamp) AS lastTimestamp, COUNT(*) AS messageCount FROM messages WHERE conversationId != '' GROUP BY conversationId ORDER BY lastTimestamp DESC")
    fun conversations():Flow<List<ConversationSummary>>
    @Insert suspend fun message(message:Message)
    @Query("DELETE FROM messages") suspend fun clearChat()
    @Query("DELETE FROM messages WHERE conversationId = :conversationId") suspend fun deleteConversation(conversationId:String)
    @Query("DELETE FROM weather") suspend fun clearWeather()
    @Query("DELETE FROM sync_metadata") suspend fun clearSyncMetadata()
    @Query("SELECT * FROM notification_receipts WHERE id = :id") suspend fun notificationReceipt(id:String):NotificationReceipt?
    @Insert(onConflict=OnConflictStrategy.REPLACE) suspend fun saveNotificationReceipt(receipt:NotificationReceipt)
    @Query("DELETE FROM notification_receipts") suspend fun clearNotificationReceipts()
    @Query("SELECT * FROM saved_places ORDER BY label") fun savedPlaces():Flow<List<SavedPlace>>
    @Insert(onConflict=OnConflictStrategy.REPLACE) suspend fun savePlace(place:SavedPlace)
    @Query("DELETE FROM saved_places") suspend fun clearPlaces()
    @Query("DELETE FROM saved_places WHERE `key` = :key") suspend fun deletePlace(key:String)
    @Query("SELECT * FROM alert_rules WHERE placeKey = :placeKey") suspend fun alertRulesOnce(placeKey:String):List<AlertRule>
    @Insert(onConflict=OnConflictStrategy.REPLACE) suspend fun saveAlertRule(rule:AlertRule)
    @Query("DELETE FROM alert_rules") suspend fun clearAlertRules()
    @Query("DELETE FROM alert_rules WHERE id = :id") suspend fun deleteAlertRule(id:String)
    @Query("DELETE FROM alert_rules WHERE placeKey = :placeKey") suspend fun deleteAlertRulesForPlace(placeKey:String)
}
@Database(entities=[SavedWeather::class,Message::class,SavedPlace::class,SyncMetadata::class,NotificationReceipt::class,AlertRule::class],version=7,exportSchema=false)
abstract class WeatherDb:RoomDatabase() { abstract fun dao():LocalDao
    companion object {
        @Volatile private var instance:WeatherDb?=null
        private val MIGRATION_1_2=object:Migration(1,2) { override fun migrate(db:SupportSQLiteDatabase) {
            db.execSQL("CREATE TABLE IF NOT EXISTS saved_places (`key` TEXT NOT NULL, `label` TEXT NOT NULL, `name` TEXT NOT NULL, `latitude` REAL NOT NULL, `longitude` REAL NOT NULL, `timezone` TEXT NOT NULL, PRIMARY KEY(`key`))")
        } }
        private val MIGRATION_2_3=object:Migration(2,3) { override fun migrate(db:SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE messages ADD COLUMN conversationId TEXT NOT NULL DEFAULT ''")
            db.execSQL("ALTER TABLE messages ADD COLUMN resolvedLocationId TEXT")
            db.execSQL("ALTER TABLE messages ADD COLUMN weatherContextTimestamp TEXT")
        } }
        private val MIGRATION_3_4=object:Migration(3,4) { override fun migrate(db:SupportSQLiteDatabase) {
            db.execSQL("CREATE TABLE IF NOT EXISTS sync_metadata (`key` TEXT NOT NULL, `etag` TEXT, `lastCheckedAt` INTEGER NOT NULL, `lastChangedAt` INTEGER NOT NULL, PRIMARY KEY(`key`))")
        } }
        private val MIGRATION_4_5=object:Migration(4,5) { override fun migrate(db:SupportSQLiteDatabase) {
            db.execSQL("CREATE TABLE IF NOT EXISTS notification_receipts (`id` TEXT NOT NULL, `contentSignature` TEXT NOT NULL, `notifiedAt` INTEGER NOT NULL, PRIMARY KEY(`id`))")
        } }
        private val MIGRATION_5_6=object:Migration(5,6) { override fun migrate(db:SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE saved_places ADD COLUMN purpose TEXT NOT NULL DEFAULT 'home'")
        } }
        private val MIGRATION_6_7=object:Migration(6,7) { override fun migrate(db:SupportSQLiteDatabase) {
            db.execSQL("CREATE TABLE IF NOT EXISTS alert_rules (`id` TEXT NOT NULL, `placeKey` TEXT NOT NULL, `channel` TEXT NOT NULL, `enabled` INTEGER NOT NULL, `updatedAt` INTEGER NOT NULL, PRIMARY KEY(`id`))")
        } }
        fun get(context:Context):WeatherDb = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(context.applicationContext,WeatherDb::class.java,"weather.db").addMigrations(MIGRATION_1_2,MIGRATION_2_3,MIGRATION_3_4,MIGRATION_4_5,MIGRATION_5_6,MIGRATION_6_7).build().also { instance=it }
        }
    }
}
/**
 * Accept a bundle only if it is usable, and say precisely why when it is not.
 *
 * The backend answers 200 with an empty bundle when every provider failed, so that case has to
 * become [ProviderUnavailableException]. Reporting it as a transport error would tell the user
 * to start a backend that already answered.
 */
fun validateBundle(data:BundleDto?,p:Place):BundleDto {
    if(data==null) throw MalformedWeatherException("Weather response was empty")
    if(data.hourly.isEmpty() || data.source_count==0) throw ProviderUnavailableException("No provider returned weather")
    if(!samePlaceCoords(data.location.latitude,data.location.longitude,p.latitude,p.longitude)) {
        throw MalformedWeatherException("Weather is for a different place")
    }
    if(!data.hourly.all { java.time.Instant.parse(it.time).epochSecond>0 && (it.temperature==null || it.temperature in -90.0..65.0) }) throw MalformedWeatherException("Weather values are out of range")
    return data
}
class Repository(context:Context) {
    val dao=WeatherDb.get(context).dao()
    val gson=Gson()
    private val client=OkHttpClient.Builder()
        .connectTimeout(if(BuildConfig.DEBUG) 4 else 12,TimeUnit.SECONDS)
        .readTimeout(35,TimeUnit.SECONDS)
        .apply {
            if(BuildConfig.DEBUG) addInterceptor { chain ->
                val request=chain.request()
                val origin="${request.url.scheme}://${request.url.host}:${request.url.port}/"
                try {
                    val response=chain.proceed(request)
                    val kind=when {
                        response.isSuccessful || response.code==304 -> NetFailure.NONE
                        else -> failureForStatus(response.code)
                    }
                    NetLog.call("http",origin,request.url.encodedPath,response.code,kind)
                    response
                } catch(error:Exception) {
                    NetLog.call("http",origin,request.url.encodedPath,null,classifyFailure(error,true),error)
                    throw error
                }
            }
        }
        .build()
    fun api(base:String):Api=Retrofit.Builder().baseUrl(normalizeBaseUrl(base,BuildConfig.API_URL)).client(client).addConverterFactory(GsonConverterFactory.create()).build().create(Api::class.java)
    @Volatile var workingBase:String?=null
    /**
     * Call [block] with a live client. In debug, a refused `10.0.2.2` connection is retried on
     * `127.0.0.1` (the `adb reverse` tunnel) and vice versa. Provider HTTP errors are not retried.
     */
    suspend fun <T> call(base:String,block:suspend (Api)->T):T {
        var last:Exception?=null
        for(url in debugAlternateBases(workingBase?:base,BuildConfig.API_URL,BuildConfig.DEBUG)) {
            try {
                val result=block(api(url))
                workingBase=url
                return result
            } catch(e:kotlinx.coroutines.CancellationException) { throw e }
            catch(e:Exception) {
                last=e
                val kind=classifyFailure(e,true)
                if(kind!=NetFailure.SERVER_UNREACHABLE && kind!=NetFailure.TIMEOUT && kind!=NetFailure.NO_NETWORK) throw e
            }
        }
        throw last ?: java.io.IOException("WeatherGPT server is not reachable")
    }
    fun key(p:Place)=placeStorageKey(p.latitude,p.longitude,p.timezone)
    /** Rematerialize weather under the stable key when GPS jitter left an orphaned Room row. */
    suspend fun ensureWeatherKey(p:Place):SavedWeather? {
        val key=key(p)
        dao.weatherOnce(key)?.let {
            CacheLog.hit(key)
            return it
        }
        val nearby=dao.allWeather().firstOrNull { row ->
            val parts=row.key.split(",")
            if(parts.size<2) return@firstOrNull false
            val lat=parts[0].toDoubleOrNull() ?: return@firstOrNull false
            val lon=parts[1].toDoubleOrNull() ?: return@firstOrNull false
            samePlaceCoords(lat,lon,p.latitude,p.longitude)
        }
        if(nearby!=null) {
            CacheLog.migrate(nearby.key,key)
            val meta=dao.syncOnce(nearby.key)
            dao.saveBundle(SavedWeather(key,nearby.json), SyncMetadata(key,meta?.etag,meta?.lastCheckedAt ?: System.currentTimeMillis(),meta?.lastChangedAt ?: System.currentTimeMillis()))
            return dao.weatherOnce(key)
        }
        CacheLog.miss(key)
        return null
    }
    suspend fun refresh(p:Place, base:String, lowData:Boolean=false) {
        ensureWeatherKey(p)
        val key=key(p)
        val hours=bundleHorizonHours(lowData)
        val existing=dao.syncOnce(key)
        var response=call(base){ it.bundle(BundleBody(p.latitude,p.longitude,p.name,p.timezone,hours),existing?.etag) }
        var checkedAt=System.currentTimeMillis()
        if(response.code()==304) {
            val localWeather=dao.weatherOnce(key) ?: ensureWeatherKey(p)
            if(canReuseNotModified(response.code(),existing,localWeather)) {
                NetLog.bundle(base,304,null,cacheHit=true,roomPresent=true,etagPresent=true)
                CacheLog.hit(key)
                dao.saveSync(checkNotNull(existing).copy(lastCheckedAt=checkedAt))
                return
            }
            // Stale ETag without a Room body must not become a permanent NO_DATA state.
            NetLog.bundle(base,304,null,cacheHit=false,roomPresent=localWeather!=null,etagPresent=existing?.etag!=null)
            if(existing!=null) dao.saveSync(existing.copy(etag=null,lastCheckedAt=checkedAt))
            response=call(base){ it.bundle(BundleBody(p.latitude,p.longitude,p.name,p.timezone,hours),null) }
            checkedAt=System.currentTimeMillis()
            if(response.code()==304) throw MalformedWeatherException("Server returned unchanged weather without a local copy")
        }
        if(!response.isSuccessful) {
            NetLog.bundle(base,response.code(),null,cacheHit=false,roomPresent=dao.weatherOnce(key)!=null,etagPresent=existing?.etag!=null)
            throw BackendHttpException(response.code(),"Weather request failed")
        }
        val data=validateBundle(response.body(),p)
        NetLog.bundle(base,response.code(),data.source_count,cacheHit=false,roomPresent=true,etagPresent=response.headers()["etag"]!=null)
        dao.saveBundle(SavedWeather(key,gson.toJson(data)),SyncMetadata(key,response.headers()["etag"],checkedAt,checkedAt))
        CacheLog.write(key,data.source_count,data.hourly.size)
    }
}


