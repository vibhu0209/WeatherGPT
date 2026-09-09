package `in`.weathergpt
import android.content.Context
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.work.*
import kotlinx.coroutines.flow.first
import java.util.concurrent.TimeUnit
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat


class CachedAlertReminder(context:Context,params:WorkerParameters):CoroutineWorker(context,params) {
    override suspend fun doWork():Result {
        val prefs=applicationContext.settings.data.first()
        if(prefs[stringPreferencesKey("official_notifications")]!="true") return Result.success()
        if(android.os.Build.VERSION.SDK_INT>=33 && ContextCompat.checkSelfPermission(applicationContext,android.Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED) return Result.success()
        val key=inputData.getString("place_key")?:return Result.success()
        val alertId=inputData.getString("alert_id")?:return Result.success()
        val repo=Repository(applicationContext)
        val bundle=repo.dao.weatherOnce(key)?.let { repo.gson.fromJson(it.json,BundleDto::class.java) }?:return Result.success()
        val alert=bundle.official_alerts.orEmpty().firstOrNull { it.id==alertId && cachedAlertIsActive(it) }?:return Result.success()
        val message=alert.instruction?:alert.description?:alert.event
        val notification=NotificationCompat.Builder(applicationContext,"official_warnings")
            .setSmallIcon(android.R.drawable.ic_dialog_alert).setContentTitle(alert.headline)
            .setContentText(message).setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setAutoCancel(true).setPriority(NotificationCompat.PRIORITY_HIGH).build()
        NotificationManagerCompat.from(applicationContext).notify(alert.id.hashCode(),notification)
        return Result.success()
    }
}

fun scheduleCachedAlerts(context:Context,place:Place,bundle:BundleDto) {
    val now=java.time.Instant.now()
    bundle.official_alerts.orEmpty().forEach { alert->
        val expires=alert.expires?.let { runCatching { java.time.Instant.parse(it) }.getOrNull() }?:return@forEach
        if(!expires.isAfter(now)) return@forEach
        val effective=alert.effective?.let { runCatching { java.time.Instant.parse(it) }.getOrNull() }?:now
        val delay=java.time.Duration.between(now,effective).toMillis().coerceAtLeast(0)
        val data=workDataOf("place_key" to Repository(context).key(place),"alert_id" to alert.id)
        val request=OneTimeWorkRequestBuilder<CachedAlertReminder>().setInputData(data).setInitialDelay(delay,TimeUnit.MILLISECONDS).addTag("official-alerts").build()
        WorkManager.getInstance(context).enqueueUniqueWork("official-alert-${alert.id.hashCode()}",ExistingWorkPolicy.REPLACE,request)
    }
}class ForecastSync(context:Context,params:WorkerParameters):CoroutineWorker(context,params) {
    override suspend fun doWork():Result {
        val prefs=applicationContext.settings.data.first()
        val repo=Repository(applicationContext)
        val saved=prefs[stringPreferencesKey("place")]?:return Result.success()
        return try {
            val p=repo.gson.fromJson(saved,Place::class.java)
            repo.refresh(p,prefs[stringPreferencesKey("server")]?:BuildConfig.API_URL)
            val bundle=repo.dao.weatherOnce(repo.key(p))?.let { repo.gson.fromJson(it.json,BundleDto::class.java) }
            bundle?.let { scheduleCachedAlerts(applicationContext,p,it) }
            val official=bundle?.official_alerts?.firstOrNull { Freshness.officialAlert(bundle.retrieved_at,it.expires)==FreshnessState.FRESH }
            if(official!=null && prefs[stringPreferencesKey("official_notifications")] == "true" && (android.os.Build.VERSION.SDK_INT<33 || ContextCompat.checkSelfPermission(applicationContext,android.Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED)) {
                val notification=NotificationCompat.Builder(applicationContext,"official_warnings")
                    .setSmallIcon(android.R.drawable.ic_dialog_alert).setContentTitle(official.headline)
                    .setContentText(official.instruction?:official.description?:official.event)
                    .setStyle(NotificationCompat.BigTextStyle().bigText(official.instruction?:official.description?:official.event))
                    .setAutoCancel(true).setPriority(NotificationCompat.PRIORITY_HIGH).build()
                NotificationManagerCompat.from(applicationContext).notify(official.id.hashCode(),notification)
            }
            if(prefs[stringPreferencesKey("risk_notifications")] == "true") {
                val risk=bundle?.risk_estimates?.firstOrNull()
                if(risk!=null && (android.os.Build.VERSION.SDK_INT<33 || ContextCompat.checkSelfPermission(applicationContext,android.Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED)) {
                    val notification=NotificationCompat.Builder(applicationContext,"local_risks")
                        .setSmallIcon(android.R.drawable.ic_dialog_alert)
                        .setContentTitle("WeatherGPT Risk Estimate")
                        .setContentText(risk.message)
                        .setStyle(NotificationCompat.BigTextStyle().bigText("${risk.message}. ${risk.rationale}. Not an official government warning."))
                        .setAutoCancel(true).build()
                    NotificationManagerCompat.from(applicationContext).notify(risk.id.hashCode(),notification)
                }
            }
            Result.success()
        } catch(e:kotlinx.coroutines.CancellationException) { throw e }
        catch(e:Exception) { if(runAttemptCount<3) Result.retry() else Result.failure() }
    }
    companion object {
        fun schedule(context:Context,wifiOnly:Boolean) {
            val job=PeriodicWorkRequestBuilder<ForecastSync>(6,TimeUnit.HOURS)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(if(wifiOnly) NetworkType.UNMETERED else NetworkType.CONNECTED).setRequiresBatteryNotLow(true).build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL,30,TimeUnit.SECONDS).build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork("forecast-sync",ExistingPeriodicWorkPolicy.UPDATE,job)
        }
    }
}


