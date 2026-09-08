package `in`.weathergpt

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

class WeatherApplication:Application() {
    override fun onCreate() {
        super.onCreate()
        if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.O) {
            val manager=getSystemService(NotificationManager::class.java)
            manager.createNotificationChannels(listOf(
                NotificationChannel("local_risks", "WeatherGPT risk estimates", NotificationManager.IMPORTANCE_DEFAULT).apply {
                    description="Calculated rain, wind, heat and visibility risks. These are not official warnings."
                },
                NotificationChannel("official_warnings", "Official weather warnings", NotificationManager.IMPORTANCE_HIGH).apply {
                    description="Reserved for connected authoritative warning feeds."
                },
                NotificationChannel("daily_forecast", "Daily forecast", NotificationManager.IMPORTANCE_LOW)
            ))
        }
    }
}
