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
        assertTrue(answer.contains("not connected"));assertFalse(answer.contains("no warnings"))
    }
    @Test fun unsupportedQuestionDoesNotInvent() {
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
}
