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
import retrofit2.http.Query as HttpQuery
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

val Context.settings by preferencesDataStore(name="preferences")
data class Place(val name:String, val latitude:Double, val longitude:Double, val timezone:String="Asia/Kolkata")
data class Hour(val time:String, val temperature:Double?, val rain_chance:Double?, val rain_mm:Double?, val wind_ms:Double?, val humidity:Double?, val source_count:Int=1, val apparent_temperature:Double?=null, val wind_direction:Double?=null, val wind_gust_ms:Double?=null, val visibility_m:Double?=null, val pressure_hpa:Double?=null, val cloud_cover:Double?=null, val uv_index:Double?=null, val weather_code:Double?=null)
data class Day(val date:String, val temperature_min:Double?, val temperature_max:Double?, val rain_chance_max:Double?, val rain_total_mm:Double?, val wind_max_ms:Double?, val humidity_average:Double?, val source_count:Int=0)
data class ScoreComponent(val name:String, val penalty:Int, val reason:String)
data class WeatherScore(val score:Int?, val label:String, val profile:String, val time_window:String?=null, val components:List<ScoreComponent>?=null, val limiting_factors:List<String>?=null, val calculated_at:String?=null, val disclaimer:String)
data class Recommendation(val severity:String, val message:String)
data class RiskEstimate(val id:String, val classification:String, val kind:String, val severity:String, val message:String, val valid_at:String, val supporting_value:Double, val unit:String, val rationale:String, val calculated_at:String, val disclaimer:String)
data class OfficialAlert(val id:String, val classification:String, val sender:String?, val sent:String?, val event:String, val headline:String, val description:String?, val instruction:String?, val severity:String, val urgency:String, val certainty:String, val effective:String?, val expires:String?, val area_descriptions:List<String>?, val source_format:String)
data class Confidence(val score:Int, val label:String, val calibrated_probability:Boolean, val reasons:List<String>)
data class BundleDto(val location:Place, val hourly:List<Hour>, val retrieved_at:String, val is_stale:Boolean, val sources:List<String>, val source_count:Int, val agreement:String, val alerts_status:String, val current:Hour?=null, val daily:List<Day>?=null, val scores:Map<String,WeatherScore>?=null, val recommendations:Map<String,List<Recommendation>>?=null, val risk_estimates:List<RiskEstimate>?=null, val confidence:Confidence?=null, val disagreement_reasons:List<String>?=null, val official_status:String?=null, val official_alerts:List<OfficialAlert>?=null, val alerts_message:String?=null)
data class SearchDto(val locations:List<Place>)
data class ResolvedPlace(val location:Place)
data class ChatBody(val text:String, val location:Place, val language:String, val profile:String, val day_offset:Int, val conversation_id:String)
data class AnswerDto(val answer:String, val language:String, val day_offset:Int, val retrieved_at:String, val is_stale:Boolean, val sources:List<String>, val agreement:String)
interface Api {
    @GET("v1/locations/search") suspend fun search(@HttpQuery("q") query:String,@HttpQuery("language") language:String): SearchDto
    @GET("v1/locations/resolve") suspend fun resolve(@HttpQuery("latitude") lat:Double,@HttpQuery("longitude") lon:Double,@HttpQuery("name") name:String):ResolvedPlace
    @GET("v1/weather/bundle") suspend fun bundle(@HttpQuery("latitude") lat:Double,@HttpQuery("longitude") lon:Double,@HttpQuery("name") name:String,@HttpQuery("timezone") timezone:String):BundleDto
    @POST("v1/chat/message") suspend fun chat(@Body body:ChatBody):AnswerDto
}
@Entity(tableName="weather") data class SavedWeather(@PrimaryKey val key:String, val json:String)
@Entity(tableName="messages") data class Message(@PrimaryKey(autoGenerate=true) val id:Long=0, val role:String, val text:String, val language:String, val timestamp:Long=System.currentTimeMillis(), val conversationId:String="", val resolvedLocationId:String?=null, val weatherContextTimestamp:String?=null)
data class ConversationSummary(val conversationId:String, val lastTimestamp:Long, val messageCount:Int)
@Entity(tableName="saved_places") data class SavedPlace(@PrimaryKey val key:String, val label:String, val name:String, val latitude:Double, val longitude:Double, val timezone:String) {
    fun place()=Place(name,latitude,longitude,timezone)
}
@Dao interface LocalDao {
    @Query("SELECT * FROM weather WHERE `key` = :key") fun weather(key:String):Flow<SavedWeather?>
    @Query("SELECT * FROM weather WHERE `key` = :key") suspend fun weatherOnce(key:String):SavedWeather?
    @Insert(onConflict=OnConflictStrategy.REPLACE) suspend fun save(weather:SavedWeather)
    @Query("SELECT * FROM messages ORDER BY id") fun messages():Flow<List<Message>>
    @Query("SELECT * FROM messages WHERE conversationId = :conversationId ORDER BY id") fun messagesFor(conversationId:String):Flow<List<Message>>
    @Query("SELECT conversationId, MAX(timestamp) AS lastTimestamp, COUNT(*) AS messageCount FROM messages WHERE conversationId != '' GROUP BY conversationId ORDER BY lastTimestamp DESC")
    fun conversations():Flow<List<ConversationSummary>>
    @Insert suspend fun message(message:Message)
    @Query("DELETE FROM messages") suspend fun clearChat()
    @Query("DELETE FROM messages WHERE conversationId = :conversationId") suspend fun deleteConversation(conversationId:String)
    @Query("DELETE FROM weather") suspend fun clearWeather()
    @Query("SELECT * FROM saved_places ORDER BY label") fun savedPlaces():Flow<List<SavedPlace>>
    @Insert(onConflict=OnConflictStrategy.REPLACE) suspend fun savePlace(place:SavedPlace)
    @Query("DELETE FROM saved_places") suspend fun clearPlaces()
}
@Database(entities=[SavedWeather::class,Message::class,SavedPlace::class],version=3,exportSchema=false)
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
        fun get(context:Context):WeatherDb = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(context.applicationContext,WeatherDb::class.java,"weather.db").addMigrations(MIGRATION_1_2,MIGRATION_2_3).build().also { instance=it }
        }
    }
}
class Repository(context:Context) {
    val dao=WeatherDb.get(context).dao()
    val gson=Gson()
    private val client=OkHttpClient.Builder().connectTimeout(12,TimeUnit.SECONDS).readTimeout(35,TimeUnit.SECONDS).build()
    fun api(base:String):Api=Retrofit.Builder().baseUrl(base).client(client).addConverterFactory(GsonConverterFactory.create()).build().create(Api::class.java)
    fun key(p:Place)="${p.latitude},${p.longitude},${p.timezone}"
    suspend fun refresh(p:Place, base:String) {
        val data=api(base).bundle(p.latitude,p.longitude,p.name,p.timezone)
        if(data.hourly.isEmpty()) throw java.io.IOException("Weather unavailable")
        require(data.location.latitude==p.latitude && data.location.longitude==p.longitude)
        require(data.hourly.all { java.time.Instant.parse(it.time).epochSecond>0 && (it.temperature==null || it.temperature in -90.0..65.0) })
        dao.save(SavedWeather(key(p),gson.toJson(data)))
    }
}


