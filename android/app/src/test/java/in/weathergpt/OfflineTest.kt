package `in`.weathergpt

import org.junit.Assert.*
import org.junit.Test
import java.time.*

class OfflineTest {
    private fun bundle():BundleDto {
        val t=LocalDate.now(ZoneId.of("Asia/Kolkata")).plusDays(1).atTime(9,0).atZone(ZoneId.of("Asia/Kolkata")).toInstant().toString()
        return BundleDto(Place("Delhi",28.6,77.2),listOf(Hour(t,31.0,65.0,2.0,3.0,60.0)),Instant.now().toString(),false,listOf("open-meteo"),1,"single_source","unavailable")
    }
    @Test fun noCacheDoesNotInventWeather() {
        val (answer,_)=Offline.answer("Rain tomorrow?",null,0)
        assertTrue(answer.contains("No saved forecast"));assertFalse(answer.contains("%"))
    }
    @Test fun tomorrowAndFollowupKeepDay() {
        val b=bundle()
        val (first,day)=Offline.answer("Weather tomorrow?",b,0)
        val (next,day2)=Offline.answer("What about morning?",b,day)
        assertEquals(1,day);assertEquals(1,day2)
        assertTrue(first.contains("65.0%"));assertTrue(next.contains("65.0%"))
        assertTrue(next.contains("may have changed"))
    }
    @Test fun unavailableAlertsAreNeverClear() {
        val (answer,_)=Offline.answer("Any alerts?",bundle(),0)
        assertTrue(answer.contains("availability is unknown"));assertFalse(answer.contains("no warnings"))
    }
    @Test fun cachedOfficialWarningKeepsInstructionsOffline() {
        val alert=OfficialAlert("cap-1","official","IMD",null,"Heavy rain","Heavy rain warning",null,"Stay indoors","severe","immediate","likely",null,Instant.now().plusSeconds(3600).toString(),listOf("Delhi"),"CAP 1.2")
        val cached=bundle().copy(official_alerts=listOf(alert),official_status="available")
        val (answer,_)=Offline.answer("Any warnings?",cached,0)
        assertTrue(answer.contains("Heavy rain warning"))
        assertTrue(answer.contains("Stay indoors"))
        assertTrue(answer.contains("New warnings and updates require"))
    }    @Test fun unsupportedQuestionDoesNotInvent() {
        val (answer,_)=Offline.answer("Make up a cyclone alert",bundle(),0)
        assertFalse(answer.contains("red warning"))
    }
    @Test fun categoryFreshnessUsesDifferentSafetyWindows() {
        val now=Instant.parse("2026-09-08T12:00:00Z")
        assertEquals(FreshnessState.FRESH,Freshness.weather("2026-09-08T11:30:00Z",now))
        assertEquals(FreshnessState.AGING,Freshness.weather("2026-09-08T10:00:00Z",now))
        assertEquals(FreshnessState.STALE,Freshness.weather("2026-09-08T08:00:00Z",now))
        assertEquals(FreshnessState.AGING,Freshness.officialAlert("2026-09-08T11:30:00Z","2026-09-08T13:00:00Z",now))
        assertEquals(FreshnessState.STALE,Freshness.officialAlert("2026-09-08T11:59:00Z","2026-09-08T12:00:00Z",now))
        assertEquals(FreshnessState.FRESH,Freshness.climate("2026-09-02T12:00:00Z",now))
    }
    @Test fun weatherCodesHavePlainLanguageCategories() {
        assertEquals(R.string.clear_sky,conditionResource(0))
        assertEquals(R.string.thunderstorm,conditionResource(95))
        assertNull(conditionResource(999))
    }
    @Test fun cachedAlertLifecycleUsesEffectiveAndExpiry() {
        val now=Instant.parse("2026-09-09T12:00:00Z")
        fun alert(effective:String?,expires:String?)=OfficialAlert("id","official","IMD",null,"Rain","Rain warning",null,"Stay inside","severe","immediate","likely",effective,expires,listOf("Delhi"),"CAP 1.2")
        assertTrue(cachedAlertIsActive(alert("2026-09-09T11:00:00Z","2026-09-09T13:00:00Z"),now))
        assertFalse(cachedAlertIsActive(alert("2026-09-09T12:30:00Z","2026-09-09T13:00:00Z"),now))
        assertFalse(cachedAlertIsActive(alert(null,"2026-09-09T12:00:00Z"),now))
    }    @Test fun officialSeverityMapsToAlertTone() {
        assertEquals(AlertLevel.RED,alertLevel("Extreme"))
        assertEquals(AlertLevel.RED,alertLevel("Severe"))
        assertEquals(AlertLevel.ORANGE,alertLevel("Moderate"))
        assertEquals(AlertLevel.YELLOW,alertLevel("Minor"))
    }    @Test fun sharedBackendContractDeserializesInAndroid() {
        val json=checkNotNull(javaClass.classLoader?.getResource("weather_bundle.json")).readText()
        val bundle=com.google.gson.Gson().fromJson(json,BundleDto::class.java)
        assertEquals("Asia/Kolkata",bundle.location.timezone)
        assertEquals(2,bundle.source_count)
        assertEquals(61.0,bundle.hourly.single().weather_code?:-1.0,0.0)
        assertEquals("severe",bundle.official_alerts?.single()?.severity)
        assertFalse(bundle.confidence?.calibrated_probability?:true)
    }
    @Test fun notModifiedRequiresMatchingLocalState() {
        val metadata=SyncMetadata("place","\"etag\"",1,1)
        val weather=SavedWeather("place","{}")
        assertTrue(canReuseNotModified(304,metadata,weather))
        assertFalse(canReuseNotModified(304,null,weather))
        assertFalse(canReuseNotModified(304,metadata,null))
        assertFalse(canReuseNotModified(200,metadata,weather))
    }
    @Test fun lowDataModeReducesHorizonAndRefreshFrequency() {
        assertEquals(72,bundleHorizonHours(true))
        assertEquals(168,bundleHorizonHours(false))
        assertEquals(12L,syncIntervalHours(true))
        assertEquals(6L,syncIntervalHours(false))
    }
}




