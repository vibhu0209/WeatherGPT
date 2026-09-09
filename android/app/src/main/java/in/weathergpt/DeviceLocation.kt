package `in`.weathergpt

import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import android.os.CancellationSignal
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

    fun request(context: Context, onResult: (Location?) -> Unit) {
        if (!hasPermission(context)) {
            onResult(null)
            return
        }
        val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val provider = when {
                manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
                manager.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
                else -> manager.getProviders(true).firstOrNull()
            }
            if (provider == null) {
                onResult(lastKnown(manager))
                return
            }
            runCatching {
                manager.getCurrentLocation(provider, CancellationSignal(), ContextCompat.getMainExecutor(context)) { location ->
                    onResult(location ?: lastKnown(manager))
                }
            }.onFailure { onResult(lastKnown(manager)) }
        } else {
            onResult(lastKnown(manager))
        }
    }
}
