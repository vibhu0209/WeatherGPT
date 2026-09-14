package `in`.weathergpt

import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.net.UnknownServiceException
import java.time.Instant
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

/**
 * Covers the Android to backend path: how failures are categorised, which single banner the user
 * sees, and that the Retrofit base URL really resolves to the endpoints the backend serves.
 */
class NetworkTest {
    private lateinit var server: MockWebServer

    private val delhi = Place("Delhi", 28.6, 77.2)

    @Before fun start() { server = MockWebServer(); server.start() }
    @After fun stop() { server.shutdown() }

    private fun api(readTimeoutMs: Long = 5000): Api {
        val client = OkHttpClient.Builder()
            .connectTimeout(2, TimeUnit.SECONDS)
            .readTimeout(readTimeoutMs, TimeUnit.MILLISECONDS)
            .build()
        return Retrofit.Builder()
            .baseUrl(server.url("/"))
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(Api::class.java)
    }

    private fun bundleJson(sourceCount: Int = 1, latitude: Double = 28.6, hours: String = """
        [{"time":"${Instant.now()}","temperature":31.0,"rain_chance":10.0,"rain_mm":0.0,"wind_ms":3.0,"humidity":60.0}]
    """.trimIndent()) = """
        {"location":{"name":"Delhi","latitude":$latitude,"longitude":77.2,"timezone":"Asia/Kolkata"},
         "hourly":$hours,"retrieved_at":"${Instant.now()}","is_stale":false,
         "sources":["open-meteo"],"source_count":$sourceCount,"agreement":"single_source",
         "alerts_status":"unavailable"}
    """.trimIndent()

    // --- base URL and path resolution (Retrofit trailing-slash rule) ---

    @Test fun healthResolvesToTheBackendPath() = runTest {
        server.enqueue(MockResponse().setBody("""{"status":"ok"}"""))
        assertEquals("ok", api().health()["status"])
        assertEquals("/health", server.takeRequest().path)
    }

    @Test fun weatherEndpointKeepsTheVersionedPrefix() = runTest {
        server.enqueue(MockResponse().setBody(bundleJson()))
        api().bundle(BundleBody(28.6, 77.2, "Delhi", "Asia/Kolkata", 72), null)
        val request = server.takeRequest()
        assertEquals("/v1/weather/bundle", request.path)
        assertEquals("POST", request.method)
    }

    @Test fun onlyABaseUrlWithAPathNeedsTheTrailingSlash() {
        // A host-only base is fine because HttpUrl normalises it to "…:8000/".
        Retrofit.Builder().baseUrl("http://10.0.2.2:8000").build()
        // With a path segment the slash is mandatory: Retrofit would otherwise resolve
        // "v1/weather/bundle" against "/api" and drop the "api" segment.
        assertThrows(IllegalArgumentException::class.java) {
            Retrofit.Builder().baseUrl("http://10.0.2.2:8000/api").build()
        }
    }

    @Test fun aBaseUrlWithAPathKeepsThatPrefix() {
        val retrofit = Retrofit.Builder().baseUrl("http://10.0.2.2:8000/api/").build()
        // Relative endpoints keep the prefix; a leading slash would throw it away, which is why
        // every annotation in Api is relative.
        assertEquals("http://10.0.2.2:8000/api/health", retrofit.baseUrl().resolve("health").toString())
        assertEquals("http://10.0.2.2:8000/health", retrofit.baseUrl().resolve("/health").toString())
    }

    // --- failure categories ---

    @Test fun healthSuccessIsNotAFailure() {
        assertEquals(WeatherNotice.NONE, noticeFor(NetFailure.NONE, hasCache = true, isStale = false))
    }

    @Test fun connectionRefusedIsAnUnreachableServerWhenOnline() {
        assertEquals(NetFailure.SERVER_UNREACHABLE, classifyFailure(ConnectException("refused"), online = true))
    }

    @Test fun theSameFailureWithoutATransportIsNoNetwork() {
        assertEquals(NetFailure.NO_NETWORK, classifyFailure(ConnectException("refused"), online = false))
        assertEquals(NetFailure.NO_NETWORK, classifyFailure(UnknownHostException("dns"), online = false))
    }

    @Test fun blockedCleartextLooksLikeAnUnreachableServer() {
        // The real regression: the debug network security config blocked http://, so OkHttp threw
        // before opening a socket and every screen claimed the backend was down.
        val error = UnknownServiceException("CLEARTEXT communication to 10.0.2.2 not permitted by network security policy")
        assertEquals(NetFailure.SERVER_UNREACHABLE, classifyFailure(error, online = true))
    }

    @Test fun readTimeoutStaysATimeout() = runTest {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
        val error = runCatching { api(readTimeoutMs = 300).health() }.exceptionOrNull()
        assertTrue("expected a timeout, got $error", error is SocketTimeoutException)
        assertEquals(NetFailure.TIMEOUT, classifyFailure(error!!, online = true))
    }

    @Test fun serverErrorIsNotAConnectionProblem() = runTest {
        server.enqueue(MockResponse().setResponseCode(500).setBody("""{"code":"internal_error"}"""))
        val response = api().bundle(BundleBody(28.6, 77.2, "Delhi", "Asia/Kolkata", 72), null)
        assertFalse(response.isSuccessful)
        assertEquals(NetFailure.SERVER_ERROR, classifyFailure(BackendHttpException(response.code(), "x"), online = true))
    }

    @Test fun upstreamOutageIsAProviderFailure() {
        // The backend maps every provider/geocoder outage onto 503.
        assertEquals(NetFailure.PROVIDER_UNAVAILABLE, failureForStatus(503))
        assertEquals(NetFailure.PROVIDER_UNAVAILABLE, failureForStatus(504))
    }

    @Test fun deviceAuthProblemsAreAConfigurationError() {
        assertEquals(NetFailure.AUTH_CONFIGURATION_ERROR, failureForStatus(401))
        assertEquals(NetFailure.AUTH_CONFIGURATION_ERROR, failureForStatus(403))
    }

    @Test fun malformedJsonIsABadResponseNotAnOutage() = runTest {
        server.enqueue(MockResponse().setBody("{ this is not json"))
        val error = runCatching { api().health() }.exceptionOrNull()
        assertNotNull(error)
        assertEquals(NetFailure.BAD_RESPONSE, classifyFailure(error!!, online = true))
    }

    // --- the rule that caused the misleading message ---

    @Test fun aReachableBackendWithNoProviderDataIsNotAnUnreachableServer() = runTest {
        server.enqueue(MockResponse().setBody(bundleJson(sourceCount = 0, hours = "[]")))
        val body = api().bundle(BundleBody(28.6, 77.2, "Delhi", "Asia/Kolkata", 72), null).body()
        val error = runCatching { validateBundle(body, delhi) }.exceptionOrNull()
        assertTrue(error is ProviderUnavailableException)
        assertEquals(NetFailure.PROVIDER_UNAVAILABLE, classifyFailure(error!!, online = true))
        assertNotEquals(NetFailure.SERVER_UNREACHABLE, classifyFailure(error, online = true))
    }

    @Test fun weatherForADifferentPlaceIsRejected() = runTest {
        server.enqueue(MockResponse().setBody(bundleJson(latitude = 19.0)))
        val body = api().bundle(BundleBody(28.6, 77.2, "Delhi", "Asia/Kolkata", 72), null).body()
        assertThrows(MalformedWeatherException::class.java) { validateBundle(body, delhi) }
    }

    @Test fun impossibleTemperaturesAreRejected() = runTest {
        val absurd = """[{"time":"${Instant.now()}","temperature":250.0,"rain_chance":0.0,"rain_mm":0.0,"wind_ms":1.0,"humidity":10.0}]"""
        server.enqueue(MockResponse().setBody(bundleJson(hours = absurd)))
        val body = api().bundle(BundleBody(28.6, 77.2, "Delhi", "Asia/Kolkata", 72), null).body()
        assertThrows(MalformedWeatherException::class.java) { validateBundle(body, delhi) }
    }

    @Test fun emptyProviderBundleIsProviderUnavailableNotTransport() {
        val empty = BundleDto(
            location = delhi,
            hourly = emptyList(),
            retrieved_at = Instant.now().toString(),
            is_stale = false,
            sources = emptyList(),
            source_count = 0,
            agreement = "none",
            alerts_status = "unavailable",
        )
        val error = assertThrows(ProviderUnavailableException::class.java) { validateBundle(empty, delhi) }
        assertEquals(NetFailure.PROVIDER_UNAVAILABLE, classifyFailure(error, online = true))
        assertEquals(WeatherNotice.PROVIDERS_UNAVAILABLE, noticeFor(NetFailure.PROVIDER_UNAVAILABLE, hasCache = false, isStale = false))
    }

    @Test fun singleSourceBundleIsAccepted() {
        val body = """{"location":{"name":"Delhi","latitude":28.6,"longitude":77.2,"timezone":"Asia/Kolkata"},"hourly":[{"time":"${Instant.now()}","temperature":30.0,"rain_chance":10.0,"rain_mm":0.0,"wind_ms":2.0,"humidity":50.0}],"retrieved_at":"${Instant.now()}","is_stale":false,"sources":["open-meteo"],"source_count":1,"agreement":"single_source","alerts_status":"unavailable"}"""
        val data = validateBundle(com.google.gson.Gson().fromJson(body, BundleDto::class.java), delhi)
        assertEquals(1, data.source_count)
    }

    @Test fun notModifiedIsOnlyReusableWithALocalCopy() = runTest {
        server.enqueue(MockResponse().setResponseCode(304))
        val response = api().bundle(BundleBody(28.6, 77.2, "Delhi", "Asia/Kolkata", 72), "\"abc\"")
        assertEquals(304, response.code())
        val metadata = SyncMetadata("k", "\"abc\"", 0, 0)
        assertTrue(canReuseNotModified(304, metadata, SavedWeather("k", "{}")))
        assertFalse(canReuseNotModified(304, metadata, null))
        assertTrue(shouldRetryUncachedNotModified(304, metadata, null))
        assertFalse(shouldRetryUncachedNotModified(304, metadata, SavedWeather("k", "{}")))
    }

    @Test fun uncachedNotModifiedMustRetryWithoutEtag() {
        val metadata = SyncMetadata("28.6,77.2,Asia/Kolkata", "\"stale\"", 1, 1)
        assertTrue(shouldRetryUncachedNotModified(304, metadata, null))
        assertTrue(shouldRetryUncachedNotModified(304, null, null))
        assertFalse(shouldRetryUncachedNotModified(200, metadata, null))
        assertFalse(shouldRetryUncachedNotModified(304, metadata, SavedWeather("k", "{}")))
    }

    // --- one banner per root cause ---

    @Test fun eachRootCauseProducesExactlyOneMessage() {
        // Case A: backend unreachable, cache present.
        assertEquals(WeatherNotice.CANT_CONNECT, noticeFor(NetFailure.SERVER_UNREACHABLE, hasCache = true, isStale = true))
        // Case B: no internet, cache present.
        assertEquals(WeatherNotice.OFFLINE_CACHED, noticeFor(NetFailure.NO_NETWORK, hasCache = true, isStale = true))
        // Case C: backend fine, provider failed, cache present.
        assertEquals(WeatherNotice.PROVIDER_DOWN, noticeFor(NetFailure.PROVIDER_UNAVAILABLE, hasCache = true, isStale = false))
        // Case D: nothing cached — keep failure classes distinct.
        assertEquals(WeatherNotice.NO_SAVED, noticeFor(NetFailure.SERVER_UNREACHABLE, hasCache = false, isStale = false))
        assertEquals(WeatherNotice.NO_SAVED, noticeFor(NetFailure.NO_NETWORK, hasCache = false, isStale = false))
        assertEquals(WeatherNotice.PROVIDERS_UNAVAILABLE, noticeFor(NetFailure.PROVIDER_UNAVAILABLE, hasCache = false, isStale = false))
        assertNotEquals(WeatherNotice.NO_DATA, noticeFor(NetFailure.NO_NETWORK, hasCache = false, isStale = false))
        assertNotEquals(WeatherNotice.NO_DATA, noticeFor(NetFailure.PROVIDER_UNAVAILABLE, hasCache = false, isStale = false))
        assertNotEquals(WeatherNotice.NO_DATA, noticeFor(NetFailure.SERVER_UNREACHABLE, hasCache = false, isStale = false))
    }

    @Test fun usableWeatherNeverShowsNoDataBanners() {
        // Sticky transport failures must degrade to "showing saved weather", not NO_DATA.
        assertEquals(WeatherNotice.CANT_CONNECT, noticeFor(NetFailure.SERVER_UNREACHABLE, hasCache = true, isStale = false))
        assertEquals(WeatherNotice.OFFLINE_CACHED, noticeFor(NetFailure.NO_NETWORK, hasCache = true, isStale = false))
        assertEquals(WeatherNotice.PROVIDER_DOWN, noticeFor(NetFailure.PROVIDER_UNAVAILABLE, hasCache = true, isStale = false))
        assertEquals(WeatherNotice.PROVIDER_DOWN, noticeFor(NetFailure.BAD_RESPONSE, hasCache = true, isStale = false))
        assertNotEquals(WeatherNotice.NO_DATA, noticeFor(NetFailure.SERVER_UNREACHABLE, hasCache = true, isStale = false))
        assertNotEquals(WeatherNotice.NO_SAVED, noticeFor(NetFailure.NO_NETWORK, hasCache = true, isStale = false))
        assertNotEquals(WeatherNotice.PROVIDERS_UNAVAILABLE, noticeFor(NetFailure.PROVIDER_UNAVAILABLE, hasCache = true, isStale = false))
        // After a successful refresh path, banner clears even if isStale is false.
        assertEquals(WeatherNotice.NONE, noticeFor(NetFailure.NONE, hasCache = true, isStale = false))
        // Room empty + unreachable → soft "no downloaded weather", not "WeatherGPT is down".
        assertEquals(WeatherNotice.NO_SAVED, noticeFor(NetFailure.SERVER_UNREACHABLE, hasCache = false, isStale = false))
        assertEquals(WeatherNotice.CANT_CONNECT, noticeFor(NetFailure.SERVER_UNREACHABLE, hasCache = true, isStale = false))
    }

    @Test fun successfulRefreshClearsPriorNoDataSemantics() {
        // Models: old failure + valid cache after 200/304 must not keep NO_DATA.
        assertEquals(WeatherNotice.NONE, noticeFor(NetFailure.NONE, hasCache = true, isStale = false))
        assertEquals(WeatherNotice.STALE, noticeFor(NetFailure.NONE, hasCache = true, isStale = true))
    }

    @Test fun everyFailureMapsToSomeNotice() {
        // A new category must not fall through to a silent screen.
        NetFailure.entries.forEach { failure ->
            val withCache = noticeFor(failure, hasCache = true, isStale = false)
            if (failure != NetFailure.NONE) assertNotEquals("$failure was silent", WeatherNotice.NONE, withCache)
        }
    }

    @Test fun trailingSlashIsAddedAndEmptyFallsBack() {
        assertEquals("http://10.0.2.2:8000/", normalizeBaseUrl("http://10.0.2.2:8000", "http://example/"))
        assertEquals("http://10.0.2.2:8000/", normalizeBaseUrl("http://10.0.2.2:8000/", "http://example/"))
        assertEquals("http://192.168.1.10:8000/", normalizeBaseUrl("  ", "http://192.168.1.10:8000/"))
        assertEquals("http://10.0.2.2:8000/", normalizeBaseUrl(null, "http://10.0.2.2:8000"))
    }

    @Test fun debugFallsBackBetweenEmulatorHostAndAdbReverse() {
        assertEquals(
            listOf("http://127.0.0.1:8000/", "http://10.0.2.2:8000/"),
            debugAlternateBases("http://10.0.2.2:8000", "http://example/", debug = true),
        )
        assertEquals(
            listOf("http://127.0.0.1:8000/", "http://10.0.2.2:8000/"),
            debugAlternateBases("http://127.0.0.1:8000/", "http://example/", debug = true),
        )
        assertEquals(
            listOf("http://192.168.1.10:8000/"),
            debugAlternateBases("http://192.168.1.10:8000/", "http://example/", debug = true),
        )
        assertEquals(
            listOf("http://10.0.2.2:8000/"),
            debugAlternateBases("http://10.0.2.2:8000/", "http://example/", debug = false),
        )
    }

    @Test fun healthHttp500IsAServerErrorNotUnreachable() = runTest {
        server.enqueue(MockResponse().setResponseCode(500).setBody("""{"status":"error"}"""))
        val error = runCatching { api().health() }.exceptionOrNull()
        assertTrue("expected HttpException, got $error", error is retrofit2.HttpException)
        assertEquals(NetFailure.SERVER_ERROR, classifyFailure(error!!, online = true))
        assertNotEquals(NetFailure.SERVER_UNREACHABLE, classifyFailure(error, online = true))
    }

    @Test fun noInternetWithCacheIsOfflineCachedNotUnreachable() {
        assertEquals(WeatherNotice.OFFLINE_CACHED, noticeFor(NetFailure.NO_NETWORK, hasCache = true, isStale = true))
        assertNotEquals(WeatherNotice.CANT_CONNECT, noticeFor(NetFailure.NO_NETWORK, hasCache = true, isStale = true))
    }

    @Test fun placeKeysSurviveGpsJitter() {
        val a = Place("Current location", 28.61261261261261, 77.20928393909416)
        val b = Place("Current location", 28.612648, 77.209291) // still rounds to same 4dp key
        assertEquals(
            placeStorageKey(a.latitude, a.longitude, a.timezone),
            placeStorageKey(b.latitude, b.longitude, b.timezone),
        )
        assertTrue(samePlaceCoords(a.latitude, a.longitude, b.latitude, b.longitude))
        val stable = normalizePlace(a)
        assertEquals(
            placeStorageKey(stable.latitude, stable.longitude, stable.timezone),
            placeStorageKey(a.latitude, a.longitude, a.timezone),
        )
    }
}
