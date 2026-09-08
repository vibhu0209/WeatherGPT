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

class ForecastSync(context:Context,params:WorkerParameters):CoroutineWorker(context,params) {
    override suspend fun doWork():Result {
        val prefs=applicationContext.settings.data.first()
        val repo=Repository(applicationContext)
        val saved=prefs[stringPreferencesKey("place")]?:return Result.success()
        return try {
            val p=repo.gson.fromJson(saved,Place::class.java)
            repo.refresh(p,prefs[stringPreferencesKey("server")]?:BuildConfig.API_URL)
            val bundle=repo.dao.weatherOnce(repo.key(p))?.let { repo.gson.fromJson(it.json,BundleDto::class.java) }
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
