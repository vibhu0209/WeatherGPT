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
        assertTrue(next.contains("You're offline") || next.contains("Using the forecast saved"))
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
    @Test fun windDisplayConvertsMetresPerSecondToKilometresPerHour() {
        assertEquals("36", formatWindKmh(10.0, java.util.Locale.US))
        assertNull(formatWindKmh(null, java.util.Locale.US))
    }
    @Test fun cachedAlertLifecycleUsesEffectiveAndExpiry() {
        val now=Instant.parse("2026-09-09T12:00:00Z")
        fun alert(effective:String?,expires:String?)=OfficialAlert("id","official","IMD",null,"Rain","Rain warning",null,"Stay inside","severe","immediate","likely",effective,expires,listOf("Delhi"),"CAP 1.2")
        assertTrue(cachedAlertIsActive(alert("2026-09-09T11:00:00Z","2026-09-09T13:00:00Z"),now))
        assertFalse(cachedAlertIsActive(alert("2026-09-09T12:30:00Z","2026-09-09T13:00:00Z"),now))
        assertFalse(cachedAlertIsActive(alert(null,"2026-09-09T12:00:00Z"),now))
    }
    @Test fun officialSeverityMapsToAlertTone() {
        assertEquals(AlertLevel.RED,alertLevel("Extreme"))
        assertEquals(AlertLevel.RED,alertLevel("Severe"))
        assertEquals(AlertLevel.ORANGE,alertLevel("Moderate"))
        assertEquals(AlertLevel.YELLOW,alertLevel("Minor"))
    }
    @Test fun weatherScoreTalkBackNamesTheScore() {
        assertEquals(
            "Weather score for the next 24 hours, 72 / 100, Moderate agreement",
            weatherScoreTalkBack("Weather score for the next 24 hours",72,"Moderate agreement","Unavailable"),
        )
        assertEquals(
            "Weather score for the next 24 hours, Unavailable, Waiting for weather",
            weatherScoreTalkBack("Weather score for the next 24 hours",null,"Waiting for weather","Unavailable"),
        )
    }
    @Test fun officialWarningTalkBackIncludesSeverity() {
        val spoken=officialWarningTalkBack("Official weather warning","severe","Heavy rain in Delhi","Stay indoors")
        assertTrue(spoken.contains("Official weather warning"))
        assertTrue(spoken.contains("Severe"))
        assertTrue(spoken.contains("Heavy rain in Delhi"))
        assertTrue(spoken.contains("Stay indoors"))
    }
    @Test fun hourlyTalkBackIncludesUnitsAndRain() {
        assertEquals(
            "3 PM, 31°C, Chance of rain 40%",
            hourlyTalkBack("3 PM","31°C","Chance of rain","40%"),
        )
    }
    @Test fun placePurposeMapsToScoreProfile() {
        assertEquals("farming",purposeToProfile("farm"))
        assertEquals("fishing",purposeToProfile("harbour"))
        assertEquals("outdoor",purposeToProfile("work"))
        assertEquals("general",purposeToProfile("home"))
    }
    @Test fun offlineSupportsEveryLanguageDraft() {
        for (lang in listOf("en","hi","bn","te","mr","ta","gu","kn","ml","pa","or")) {
            val (answer,_)=Offline.answer("Rain tomorrow?",bundle(),0,lang)
            assertTrue(lang, answer.contains("31.0") || answer.contains("31"))
            assertTrue(lang, answer.contains("65.0%") || answer.contains("65%"))
            assertTrue(lang, answer.contains("°C"))
            if (lang!="en") {
                assertFalse(lang, answer.startsWith("Saved forecast from"))
            }
        }
    }
    @Test fun speechLocaleTagsAreRegional() {
        assertEquals("hi-IN", speechLocaleTag("hi"))
        assertEquals("or-IN", speechLocaleTag("or"))
        assertEquals("en-IN", speechLocaleTag("en"))
    }
    @Test fun availableEmptyAlertsStayHonestOffline() {
        val cached=bundle().copy(official_status="available",alerts_status="available",official_alerts=emptyList())
        val (answer,_)=Offline.answer("Any alerts?",cached,0)
        assertTrue(answer.contains("no active official warning") || answer.contains("Refresh before"))
        assertFalse(answer.contains("availability is unknown"))
    }
    @Test fun sharedBackendContractDeserializesInAndroid() {
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
        assertTrue(shouldRetryUncachedNotModified(304,metadata,null))
        assertFalse(shouldRetryUncachedNotModified(304,metadata,weather))
    }
    @Test fun lowDataModeReducesHorizonAndRefreshFrequency() {
        assertEquals(72,bundleHorizonHours(true))
        assertEquals(168,bundleHorizonHours(false))
        assertEquals(12L,syncIntervalHours(true))
        assertEquals(6L,syncIntervalHours(false))
    }
    @Test fun notificationReceiptsSuppressOnlyUnchangedContent() {
        val signature=notificationContentSignature("Flood warning","severe","Move to shelter")
        assertEquals(64,signature.length)
        assertTrue(shouldDeliverNotification(null,signature))
        assertFalse(shouldDeliverNotification(NotificationReceipt("official:id",signature,1),signature))
        assertTrue(shouldDeliverNotification(NotificationReceipt("official:id",signature,1),notificationContentSignature("Flood warning","extreme","Move now")))
    }
    @Test fun enabledAlertRuleAllowsMatchingChannel() {
        val rule=AlertRule("delhi:severe","delhi",ALERT_CHANNEL_OFFICIAL,true)
        assertTrue(alertRuleAllows(listOf(rule),"delhi",ALERT_CHANNEL_OFFICIAL,false))
    }
    @Test fun disabledAlertRuleBlocksMatchingChannel() {
        val rule=AlertRule("delhi:severe","delhi",ALERT_CHANNEL_OFFICIAL,false)
        assertFalse(alertRuleAllows(listOf(rule),"delhi",ALERT_CHANNEL_OFFICIAL,true))
    }
    @Test fun otherPlaceOrChannelDoesNotMatch() {
        val rule=AlertRule("delhi:severe","delhi",ALERT_CHANNEL_OFFICIAL,true)
        assertFalse(alertRuleAllows(listOf(rule),"mumbai",ALERT_CHANNEL_OFFICIAL,false))
        assertFalse(alertRuleAllows(listOf(rule),"delhi",ALERT_CHANNEL_RISK,false))
    }
    @Test fun missingRuleFallsBackToPreference() {
        assertTrue(alertRuleAllows(emptyList(),"delhi",ALERT_CHANNEL_OFFICIAL,true))
        assertFalse(alertRuleAllows(emptyList(),"delhi",ALERT_CHANNEL_OFFICIAL,false))
    }
    @Test fun matchingRuleStillDeduplicatesUnchangedContent() {
        val rule=AlertRule("delhi:severe","delhi",ALERT_CHANNEL_OFFICIAL,true)
        val signature=notificationContentSignature("Flood warning","severe","Move")
        val previous=NotificationReceipt("official:flood",signature,1)
        assertFalse(shouldNotifyForChannel(listOf(rule),"delhi",ALERT_CHANNEL_OFFICIAL,true,previous,signature))
        assertTrue(shouldNotifyForChannel(listOf(rule),"delhi",ALERT_CHANNEL_OFFICIAL,true,null,signature))
        assertFalse(shouldNotifyForChannel(listOf(rule.copy(enabled=false)),"delhi",ALERT_CHANNEL_OFFICIAL,true,null,signature))
    }
    @Test fun shouldPromptForPlaceOnlyAfterPreferencesLoadWithoutAPlace() {
        assertFalse(shouldPromptForPlace(false,null))
        assertFalse(shouldPromptForPlace(true,"{\"name\":\"Delhi\"}"))
        assertTrue(shouldPromptForPlace(true,null))
        assertTrue(shouldPromptForPlace(true,""))
    }
    @Test fun placeSearchRequiresOnlineAndMinChars() {
        assertFalse(shouldRunPlaceSearch("D",true))
        assertFalse(shouldRunPlaceSearch("Delhi",false))
        assertTrue(shouldRunPlaceSearch("De",true))
        assertTrue(placeSearchUnavailableOffline(false))
        assertFalse(placeSearchUnavailableOffline(true))
        assertEquals(400L, PLACE_SEARCH_DEBOUNCE_MS)
    }
    @Test fun localPlaceFallbackMatchesPopularCities() {
        assertEquals(listOf("Delhi"), localPlaceMatches("del").map { it.name })
        assertTrue(localPlaceMatches("mu").any { it.name == "Mumbai" })
        assertTrue(localPlaceMatches("x").isEmpty())
        assertEquals("en", searchLanguageTag("en-IN"))
        assertEquals("hi", searchLanguageTag("hi"))
        assertEquals("en", searchLanguageTag("xx"))
    }
    @Test fun placeSearchEmptyAndFailureStates() {
        assertTrue(placeSearchShowsEmpty(emptyList(),"no_places"))
        assertFalse(placeSearchShowsEmpty(listOf(Place("Delhi",28.6,77.2)),"no_places"))
        assertTrue(placeSearchShowsFailure("search_failed"))
        assertTrue(placeSearchShowsFailure("location_failed"))
        assertFalse(placeSearchShowsFailure(""))
    }
    @Test fun savedPlacesRemainUsableWhenBackendSearchFails() {
        val saved=listOf(SavedPlace("k","Home","Delhi",28.6,77.2,"Asia/Kolkata","home"))
        assertTrue(savedPlacesRemainUsable(saved))
        assertFalse(savedPlacesRemainUsable(emptyList()))
        assertEquals("Delhi", saved.first().place().name)
    }
    @Test fun stripUncertaintyBoilerplateRemovesRepeatedConfidenceCopy() {
        val raw = "Go between 6–8 AM.\n\nWeather sources disagree on exact timing.\nTreat this outlook as less certain.\nModels differ a little on timing — the recommended window still stands."
        val cleaned = stripUncertaintyBoilerplate(raw)
        assertTrue(cleaned.contains("Go between 6–8 AM"))
        assertFalse(cleaned.contains("Weather sources disagree"))
        assertFalse(cleaned.contains("less certain"))
        assertFalse(cleaned.contains("Models differ"))
    }
    @Test fun primaryAdviceSkipsDisagreementTips() {
        val tips = listOf(
            Recommendation("information", "Models differ a little on timing.", rule = "sources_disagree"),
            Recommendation("action", "Best outdoor window is morning.", rule = "outdoor_window"),
        )
        assertEquals("Best outdoor window is morning.", primaryAdviceMessage(tips))
        assertTrue(shouldShowConfidenceNote(bundle().copy(agreement = "sources_disagree")))
        assertFalse(shouldShowConfidenceNote(bundle().copy(agreement = "multi_source_consensus", confidence = Confidence(80, "High", false, emptyList()))))
    }
}




