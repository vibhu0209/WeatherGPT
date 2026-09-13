package `in`.weathergpt

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.util.Log
import com.google.gson.JsonParseException
import com.google.gson.stream.MalformedJsonException
import java.io.IOException
import java.net.ConnectException
import java.net.NoRouteToHostException
import java.net.PortUnreachableException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.net.UnknownServiceException
import javax.net.ssl.SSLException
import retrofit2.HttpException

/**
 * Why a backend call failed.
 *
 * The distinction that matters for honesty is [SERVER_UNREACHABLE] (we never spoke to the
 * backend) versus [PROVIDER_UNAVAILABLE] (the backend answered, but it had no weather to give).
 * Reporting the second as the first tells the user to start a server that is already running.
 */
enum class NetFailure {
    NONE,
    NO_NETWORK,
    SERVER_UNREACHABLE,
    TIMEOUT,
    SERVER_ERROR,
    PROVIDER_UNAVAILABLE,
    AUTH_CONFIGURATION_ERROR,
    BAD_RESPONSE,
}

/** The backend answered but reported no usable provider data. Not a connectivity failure. */
class ProviderUnavailableException(message: String) : IOException(message)

/** The backend answered with something we cannot trust (bad shape, wrong place, absurd values). */
class MalformedWeatherException(message: String) : IOException(message)

/** The backend answered with an HTTP error status. [code] drives the category. */
class BackendHttpException(val code: Int, message: String) : IOException(message)

/**
 * Retrofit requires a trailing slash. An empty Settings override falls back to the build default.
 * This is the single place that turns whatever the user typed into a legal base URL.
 */
fun normalizeBaseUrl(raw: String?, fallback: String): String {
    var value = raw?.trim().orEmpty()
    if (value.isEmpty()) value = fallback.trim()
    if (value.isNotEmpty() && !value.endsWith("/")) value += "/"
    return value
}

/**
 * Extra hosts to try in debug when the preferred address cannot be reached.
 *
 * On the emulator, `10.0.2.2` is the host but Windows Firewall often blocks that inbound
 * TCP. `adb reverse tcp:<port> tcp:<port>` then makes `127.0.0.1:<port>` on the emulator
 * reach the same backend without a firewall change. The reverse is also tried.
 *
 * Release builds never fall back: they use the configured HTTPS URL only.
 */
fun debugAlternateBases(preferred: String, fallback: String, debug: Boolean): List<String> {
    val primary = normalizeBaseUrl(preferred, fallback)
    if (!debug) return listOf(primary)
    val uri = runCatching { java.net.URI(primary) }.getOrNull() ?: return listOf(primary)
    if (uri.scheme != "http") return listOf(primary)
    val host = uri.host ?: return listOf(primary)
    val port = if (uri.port > 0) uri.port else 80
    val hosts = linkedSetOf<String>()
    when (host) {
        // Prefer the adb-reverse loopback: it fails immediately if the tunnel is absent,
        // and it is the path that works on Windows when the firewall blocks 10.0.2.2.
        "10.0.2.2", "127.0.0.1", "localhost" -> {
            hosts.add("127.0.0.1")
            hosts.add("10.0.2.2")
        }
        else -> hosts.add(host)
    }
    return hosts.map { "${uri.scheme}://$it:$port/" }
}

/** True when the device currently has a validated internet-capable transport. */
fun hasNetwork(context: Context): Boolean {
    val manager = context.getSystemService(ConnectivityManager::class.java) ?: return true
    val capabilities = manager.getNetworkCapabilities(manager.activeNetwork) ?: return false
    return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
        capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
}

fun failureForStatus(code: Int): NetFailure = when {
    code == 401 || code == 403 -> NetFailure.AUTH_CONFIGURATION_ERROR
    code == 408 -> NetFailure.TIMEOUT
    // The backend maps every upstream weather/geocoding outage onto 503.
    code == 502 || code == 503 || code == 504 -> NetFailure.PROVIDER_UNAVAILABLE
    else -> NetFailure.SERVER_ERROR
}

/**
 * Map a thrown error onto a category.
 *
 * [online] comes from the connectivity manager so a genuinely offline device is not blamed on
 * the backend. A socket timeout stays [NetFailure.TIMEOUT] either way, because a half-open
 * connection tells us something different from having no transport at all.
 */
fun classifyFailure(error: Throwable, online: Boolean): NetFailure = when (error) {
    is ProviderUnavailableException -> NetFailure.PROVIDER_UNAVAILABLE
    is MalformedWeatherException -> NetFailure.BAD_RESPONSE
    is BackendHttpException -> failureForStatus(error.code)
    is HttpException -> failureForStatus(error.code())
    is SocketTimeoutException -> NetFailure.TIMEOUT
    // Gson's MalformedJsonException extends IOException, so it has to be matched before the
    // generic IOException branch or a bad payload gets blamed on the network.
    is JsonParseException, is MalformedJsonException -> NetFailure.BAD_RESPONSE
    // Cleartext blocked by the network security policy. The socket is never opened, so this is
    // a client configuration fault even though it looks like an unreachable server.
    is UnknownServiceException -> NetFailure.SERVER_UNREACHABLE
    is UnknownHostException -> if (online) NetFailure.SERVER_UNREACHABLE else NetFailure.NO_NETWORK
    is ConnectException, is NoRouteToHostException, is PortUnreachableException, is SSLException ->
        if (online) NetFailure.SERVER_UNREACHABLE else NetFailure.NO_NETWORK
    is IOException -> if (online) NetFailure.SERVER_UNREACHABLE else NetFailure.NO_NETWORK
    else -> NetFailure.BAD_RESPONSE
}

/** The single banner the UI shows, so one root cause never produces three stacked warnings. */
enum class WeatherNotice {
    NONE,
    STALE,
    OFFLINE_CACHED,
    CANT_CONNECT,
    PROVIDER_DOWN,
    /** Backend unreachable/timeout and nothing saved locally. */
    NO_DATA,
    /** Device is offline and nothing saved locally. */
    NO_SAVED,
    /** Backend answered but no usable provider weather, and nothing saved locally. */
    PROVIDERS_UNAVAILABLE,
    CHECK_SETTINGS,
}

/**
 * Collapse the failure and what Room actually holds into one message.
 *
 * Hard failures stay distinct. Usable Room weather must never produce NO_DATA /
 * NO_SAVED / PROVIDERS_UNAVAILABLE — those banners claim there is nothing to show.
 */
fun noticeFor(failure: NetFailure, hasCache: Boolean, isStale: Boolean): WeatherNotice {
    val notice = when (failure) {
        NetFailure.NONE -> if (isStale) WeatherNotice.STALE else WeatherNotice.NONE
        NetFailure.AUTH_CONFIGURATION_ERROR -> WeatherNotice.CHECK_SETTINGS
        NetFailure.NO_NETWORK -> if (hasCache) WeatherNotice.OFFLINE_CACHED else WeatherNotice.NO_SAVED
        NetFailure.SERVER_UNREACHABLE, NetFailure.TIMEOUT ->
            if (hasCache) WeatherNotice.CANT_CONNECT else WeatherNotice.NO_DATA
        NetFailure.PROVIDER_UNAVAILABLE ->
            if (hasCache) WeatherNotice.PROVIDER_DOWN else WeatherNotice.PROVIDERS_UNAVAILABLE
        NetFailure.SERVER_ERROR, NetFailure.BAD_RESPONSE ->
            if (hasCache) WeatherNotice.PROVIDER_DOWN else WeatherNotice.NO_DATA
    }
    if (!hasCache) return notice
    // Invariant: weather is on screen — never claim "no data".
    return when (notice) {
        WeatherNotice.NO_DATA, WeatherNotice.NO_SAVED, WeatherNotice.PROVIDERS_UNAVAILABLE -> when (failure) {
            NetFailure.NO_NETWORK -> WeatherNotice.OFFLINE_CACHED
            NetFailure.SERVER_UNREACHABLE, NetFailure.TIMEOUT -> WeatherNotice.CANT_CONNECT
            NetFailure.PROVIDER_UNAVAILABLE, NetFailure.SERVER_ERROR, NetFailure.BAD_RESPONSE -> WeatherNotice.PROVIDER_DOWN
            NetFailure.AUTH_CONFIGURATION_ERROR -> WeatherNotice.CHECK_SETTINGS
            NetFailure.NONE -> if (isStale) WeatherNotice.STALE else WeatherNotice.NONE
        }
        else -> notice
    }
}

/** Debug-only: why the single status banner is (or is not) showing. */
fun logNoticeState(
    notice: WeatherNotice,
    failure: NetFailure,
    hasWeather: Boolean,
    isStale: Boolean,
    offline: Boolean,
    backendOnline: Boolean?,
    refreshing: Boolean,
) {
    if (!BuildConfig.DEBUG) return
    android.util.Log.d(
        "WeatherGPTNotice",
        "notice=$notice failure=$failure hasWeather=$hasWeather isStale=$isStale " +
            "offline=$offline backendOnline=$backendOnline refreshing=$refreshing",
    )
}

/**
 * Debug-build network tracing.
 *
 * Release builds log nothing. Even in debug this records only the host, port, path and outcome:
 * no query string (which can carry a place name), no headers, no body, no coordinates, no tokens.
 */
object NetLog {
    private const val TAG = "WeatherGPTNet"

    fun call(operation: String, base: String, path: String, status: Int?, failure: NetFailure, error: Throwable? = null) {
        if (!BuildConfig.DEBUG) return
        val uri = runCatching { java.net.URI(base) }.getOrNull()
        val port = uri?.port?.takeIf { it > 0 } ?: if (uri?.scheme == "https") 443 else 80
        val detail = error?.let { " exception=${it.javaClass.simpleName} detail=${redact(it.message)}" }.orEmpty()
        Log.d(TAG, "$operation scheme=${uri?.scheme} host=${uri?.host} port=$port path=$path " +
            "status=${status ?: "-"} failure=$failure$detail")
    }

    fun bundle(
        base: String,
        status: Int?,
        sourceCount: Int?,
        cacheHit: Boolean,
        roomPresent: Boolean,
        etagPresent: Boolean,
    ) {
        if (!BuildConfig.DEBUG) return
        val uri = runCatching { java.net.URI(base) }.getOrNull()
        val port = uri?.port?.takeIf { it > 0 } ?: if (uri?.scheme == "https") 443 else 80
        Log.d(
            TAG,
            "bundle_diag scheme=${uri?.scheme} host=${uri?.host} port=$port path=v1/weather/bundle " +
                "status=${status ?: "-"} source_count=${sourceCount ?: "-"} cache_hit=$cacheHit " +
                "room_bundle=$roomPresent etag=$etagPresent",
        )
    }

    /** Drop query strings and anything that looks like a coordinate pair. */
    private fun redact(message: String?): String {
        if (message.isNullOrBlank()) return "-"
        return message.substringBefore('?').replace(Regex("-?\\d+\\.\\d{3,}"), "<redacted>").take(180)
    }
}
