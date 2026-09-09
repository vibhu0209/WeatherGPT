package `in`.weathergpt

import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import android.os.CancellationSignal
import android.os.Handler
import android.os.Looper
import androidx.core.content.ContextCompat

object DeviceLocation {
    fun hasPermission(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, android.Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    fun lastKnown(manager: LocationManager): Location? =
        runCatching {
            manager.getProviders(true)
                .mapNotNull { provider -> runCatching { manager.getLastKnownLocation(provider) }.getOrNull() }
                .maxByOrNull { it.time }
        }.getOrNull()

    fun request(context: Context, onResult: (Location?) -> Unit, timeoutMs: Long = 8000L) {
        if (!hasPermission(context)) {
            onResult(null)
            return
        }
        val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        var finished = false
        fun finish(location: Location?) {
            if (finished) return
            finished = true
            onResult(location)
        }
        Handler(Looper.getMainLooper()).postDelayed({
            finish(lastKnown(manager))
        }, timeoutMs)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val providers = listOfNotNull(
                LocationManager.NETWORK_PROVIDER.takeIf { manager.isProviderEnabled(it) },
                LocationManager.GPS_PROVIDER.takeIf { manager.isProviderEnabled(it) },
            ).ifEmpty { manager.getProviders(true) }
            if (providers.isEmpty()) {
                finish(lastKnown(manager))
                return
            }
            var remaining = providers.size
            providers.forEach { provider ->
                runCatching {
                    manager.getCurrentLocation(provider, CancellationSignal(), ContextCompat.getMainExecutor(context)) { location ->
                        if (location != null) finish(location)
                        else {
                            remaining -= 1
                            if (remaining <= 0) finish(lastKnown(manager))
                        }
                    }
                }.onFailure {
                    remaining -= 1
                    if (remaining <= 0) finish(lastKnown(manager))
                }
            }
        } else {
            finish(lastKnown(manager))
        }
    }
}
