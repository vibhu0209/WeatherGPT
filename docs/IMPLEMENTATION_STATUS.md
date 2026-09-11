# Implementation status

This is an implementation in progress, not completion of the entire master specification. No feature below is silently treated as complete.

User override: all work directly in D:/WeatherGPT; **demo mode (sections 68–69) is skipped** and is not required for this fork; light/dark/system themes and inclusive UI prioritized.

Status words used below:

| Label | Means |
|---|---|
| IMPLEMENTED | Code exists and is wired to a caller |
| TESTED | Automated tests cover the path |
| VERIFIED ON DEVICE | Exercised on the Pixel_10a emulator (API 37) |
| UNVERIFIED ON DEVICE | Code exists; no complete device observation |
| CREDENTIAL-BLOCKED | Adapter exists; live use needs keys/agreements |
| SKIPPED | Explicitly out of scope for this fork |

Provider honesty:

| Provider | Adapter | Live verified here | Production-capable | Notes |
|---|---|---|---|---|
| Open-Meteo GFS | yes | yes | yes | Default, no key |
| OpenWeather | yes | yes (with key) | yes when keyed | CREDENTIAL-BLOCKED without `OPENWEATHER_API_KEY` |
| WeatherAPI | yes | yes (with key) | yes when keyed | CREDENTIAL-BLOCKED without `WEATHERAPI_KEY` |
| ECMWF IFS via Open-Meteo | yes | yes | yes | Independent model family, not a fourth primary agency |
| IMD forecasts | probe only | no | no | **Not** a completed fourth live provider |
| IMD CAP RSS | parser + HTTP | yes when `CAP_ALERT_URL` set | feed-dependent | Official warnings, not IMD station forecasts |
| Open-Meteo Marine | yes | yes | model guidance only | Not INCOIS |
| INCOIS marine | no | no | no | CREDENTIAL-BLOCKED / absent |
| BHASHINI / Google Translate | yes | no | no | CREDENTIAL-BLOCKED |
| Gemini wording | yes | yes when keyed | optional | Never weather ground truth |
| FCM / SMS | disabled stubs | no | no | CREDENTIAL-BLOCKED |

> Same-day sources: `docs/FINAL_AUDIT.md`, `docs/REMAINING_WORK.md`, `docs/audit_status.json`, `docs/EVALUATION.md`. They must agree with this file.

## Verified so far (re-measured 2026-09-11 dead-code pass)
- Backend: **174 tests passed**. Localization integrity: **11 languages × 170/170** with English-leftover gate. Every remaining Android string key is referenced from Kotlin or layouts.
- Android: `assembleDebug` **passed** (`android/app/build/outputs/apk/debug/app-debug.apk`, 19.86 MB) on 2026-09-11 after this pass. `testDebugUnitTest` **52 passed** (`OfflineTest` 27 + `NetworkTest` 25), `lintDebug` **passed** (0 errors, 35 warnings, 2 hints).
- Emulator: Pixel_10a (`sdk_gphone16k_x86_64`, API 37). Fresh install, Hindi → Farming → Delhi, chat, Mumbai/Delhi compare, airplane-mode restart with cached forecast, DEMO notification, Bengali + Fishing home, ERA5 climate, forecast disagreement 66/100, Google Speech UI. This pass did **not** re-run the emulator; UI wiring (Home alerts honesty, Forecast gust/visibility/UV, chat post-answer chips) is in the rebuilt APK and UNVERIFIED ON DEVICE until the next device run.
- Live verification: 4-provider fusion; ERA5 climate (+0.49 °C/decade Mumbai); Open-Meteo Marine (0.72 m); IMD CAP feed; Gemini optional with facts/prose split.
- Adversarial/security subset **24 passed** including live-device-id 409. APK scanned: no secrets. Server logs grepped: no coordinates.
- **Still open:** spoken voice transcript, portable Gradle URL, instrumentation tests, live BHASHINI, FCM/IMD/INCOIS credentials.
- Live providers with local `.env`: OpenWeather + WeatherAPI + Open-Meteo/ECMWF; CAP IMD RSS connected; Gemini polish enabled.
- Full-screen onboarding: **three** steps — language → occupation → location. Theme (`system`) and large text (`true`) are set automatically. Notification permission is requested from Settings, not onboarding.
- Room v7 alert rules are **read by ForecastSync / CachedAlertReminder** (enabled rule or preference fallback). JVM tests cover match / no-match / duplicate. Device firing of a rule-gated official alert is UNVERIFIED ON DEVICE (DEMO notification was verified separately).
- Docs: SECURITY, PRIVACY, SCALABILITY, THREAT_MODEL, API, LANGUAGE_SUPPORT, GEMINI_TUNING, README refreshed. Home/Forecast/chat strings that had no UI path are now connected or removed.

## Credential blockers (honest)
| Integration | Status |
|---|---|
| IMD normalized forecasts | CREDENTIAL-BLOCKED — access probe only; not a live fourth provider |
| IMD CAP official warnings | LIVE when `CAP_ALERT_URL` + allowlist are set (this machine: yes). Not IMD station forecasts |
| Gemini live wording | Optional; adapter + guardrails tested; disabled without `GEMINI_API_KEY` + `GEMINI_MODEL` |
| BHASHINI / Google Translation live | CREDENTIAL-BLOCKED — fixture-tested adapters, deterministic drafts without keys |
| FCM push | CREDENTIAL-BLOCKED — disabled stub; needs `FIREBASE_*` |
| SMS delivery | CREDENTIAL-BLOCKED — disabled stub; needs `SMS_*` |
| INCOIS official marine | CREDENTIAL-BLOCKED / absent — Open-Meteo Marine is model sea state only |

## Master requirement coverage
| Section | Status | Detail |
|---|---|---|
| 1. AUTHORITATIVE PRODUCT OBJECTIVE | IN PROGRESS | Foundation and persistent specification recorded; full product requirements remain. |
| 2. NON-NEGOTIABLE PRODUCT PRINCIPLES | IN PROGRESS | Validated-data-only, official-warning precedence, offline honesty, no demo mode per user override. |
| 3. FIRST ACTION — INSPECT THE DEVELOPMENT ENVIRONMENT | IN PROGRESS | Local Python, Android SDK/tools and Gradle distribution recorded; environment drifts over time. |
| 4. RESEARCH BEFORE IMPLEMENTATION | IN PROGRESS | Official core docs checked; remaining source research outstanding. |
| 5. REPOSITORY STRUCTURE | IN PROGRESS | Android + FastAPI layout in D:/WeatherGPT; nested folder unused. |
| 6. PERSISTENT AGENT INSTRUCTIONS | IMPLEMENTED | AGENTS.md and workspace rules active. |
| 7. IMPLEMENTATION STATUS TRACKER | IMPLEMENTED | This document. |
| 8. HIGH-LEVEL ARCHITECTURE | IN PROGRESS | Chat-first Android → FastAPI → providers; Room offline; production scale remains. |
| 9. ANDROID APPLICATION | IMPLEMENTED | Native Compose app. `assembleDebug` / `lintDebug` / `testDebugUnitTest` **passed**; debug APK exists. Emulator journey VERIFIED ON DEVICE (Pixel_10a / API 37). Spoken voice turn UNVERIFIED. |
| 10. BACKEND | IMPLEMENTED | FastAPI live; 174 pytest; optional Redis/SQLite. Production horizontal scale remains limited. |
| 11. FOUR PRIMARY WEATHER API INTEGRATIONS | IN PROGRESS | **Adapters exist** for Open-Meteo, OpenWeather, WeatherAPI, IMD probe + ECMWF IFS. **Live verified:** Open-Meteo, OpenWeather, WeatherAPI, ECMWF IFS (four model sources). **IMD forecasts are not a completed live provider.** |
| 12. SPECIALIST METEOROLOGICAL SOURCES | IN PROGRESS | Open-Meteo Marine adapter live-tested for model sea state; official INCOIS/IMD specialist feeds and agromet remain. |
| 13. PROVIDER ADAPTER CONTRACT | TESTED | The four primary adapters plus an independent ECMWF IFS model adapter implement typed identity, capabilities, health, current/hourly/daily/alerts/historical methods; provider data is normalized before Android. |
| 14. CANONICAL WEATHER DATA MODELS | IN PROGRESS | Validated temperature, apparent temperature, precipitation, wind/gust/direction, humidity, visibility, pressure, cloud, UV and weather-code fields; broader model set pending. |
| 15. LOCATION AND TIME CORRECTNESS | IN PROGRESS | UTC storage and location-timezone selection tested; GET/POST resolve; Room-backed saved places; IMD station distance remains. |
| 16. DATA VALIDATION | IN PROGRESS | Invalid values and stale forecast rejection tested. |
| 17. WEATHER FUSION ENGINE | TESTED | Configured weighted median consensus, weighted categorical voting, weighted circular wind direction, duplicate-model exclusion, time alignment and disagreement detection are tested. Initial weights remain equal until representative observations justify calibration. |
| 18. FORECAST CONFIDENCE | TESTED | Explainable source coverage/agreement score and disagreement reasons implemented and tested; explicitly labelled as uncalibrated and not a probability. |
| 19. PROVIDER ACCURACY EVALUATION | TESTED | Typed samples and MAE, bias, RMSE, rain Brier, availability and latency metrics are tested; no weighting is applied without representative observations. |
| 20. ALERT ENGINE | IN PROGRESS | Official warnings and local risks are separate; unavailable sources never imply no warning. CAP lifecycle and polygon tests pass; production authority feed validation remains. |
| 21. COMMON ALERTING PROTOCOL | TESTED | CAP 1.2 parsing, active-time checks, polygon filtering, cancellation rejection, classification and severity ordering have unit coverage. Trusted live feed configuration remains external. |
| 22. DETERMINISTIC LOCAL RISK RULES | TESTED | Heavy hourly rain, strong wind, heat and poor visibility thresholds produce attributed WeatherGPT Risk Estimates; missing/below-threshold data produces none. |
| 23. ONBOARDING / STARTING FORM | IN PROGRESS | Full-screen flow with **three** steps: language → occupation → location (search, quick cities, or device location). Theme (`system`) and large text (`true`) are set automatically, **not chosen**, and notification permission is **not** requested during onboarding — it is requested from Settings. |
| 24. PROFILE PERSONALIZATION | IMPLEMENTED | Eleven occupation profiles; per-place purpose (Home/Farm/Harbour/Work) stored in Room v6 and maps into score profile. |
| 25. WEATHER SCORE | TESTED | Bounded deterministic 24-hour score for all profiles; fishing score uses marine wave/swell when available and never certifies safety. |
| 26. PROFILE-SPECIFIC SCORE COMPONENTS | TESTED | Farming/outdoor/construction/emergency/tourism/transport/vendor matrix plus fishing marine penalties and spray-window helper tested. |
| 27. OCCUPATION DECISION SUPPORT ENGINE | TESTED | Grounded recommendations from weather variable + local time window + configured rule + source. Farming spray/harvest windows, fishing marine-required (never a clearance), construction rain/lightning/wind/heat, tourism outdoor/UV, transport visibility, vendor rain/heat/wind, general practical timing. Official warnings precede; unknown warning source is not “no warnings”. Chat uses 11-language templates. Gemini does not invent advice. |
| 28. CHATBOT — PRIMARY APPLICATION EXPERIENCE | IN PROGRESS | Chat default tab, suggestions, text, speech transcript and playback; device voice QA remains. |
| 29. CHAT RESPONSE DESIGN | IMPLEMENTED | Natural-language answer with listen control. After a thread (font scale under 1.5), chips send hourly / warnings / score questions through the same chat path. |
| 30. MULTI-TURN CONVERSATION | IN PROGRESS | Persistent conversation state in Room; live follow-ups hold the day. Context is still `day_offset` + location only. **Android compare chips** call `setComparePlace()`; emulator compared Mumbai vs Delhi (30.5°C / 21% vs 35.9°C / 29%). |
| 31. WEATHER CHAT TOOLS | TESTED | All 12 `TOOL_REGISTRY` tools are reachable from `POST /v1/chat/message` via `select_tool` / `invoke_registered_tool`. Forecast tools still use `chat.answer()` after invocation. Tests in `test_chat_tools.py`. |
| 32. CHAT EXECUTION PIPELINE | IN PROGRESS | Deterministic intent/time resolution, verified weather execution, official-alert enrichment before warning answers, guarded optional wording and fallback are implemented; full model tool orchestration remains. |
| 33. GEMINI INTEGRATION | IN PROGRESS | Optional backend-only wording pass. Facts and rewordable prose are split; boilerplate-only drafts skip the API. `validate_polish` is unchanged. 429 opens a circuit and is never retried. Free-tier quota remains limited. |
| 34. GEMINI SYSTEM GUARDRAIL | TESTED | Dedicated prompt restricts output to verified draft facts and preserves warning boundaries. |
| 35. LLM RESPONSE VALIDATION | IN PROGRESS | Schema, length, supplied-number, number-unit pairing, named-source retention, warning-severity retention and false-warning validation are tested; full natural-language entailment remains. |
| 36. GEMINI FAILURE FALLBACK | TESTED | Missing credentials, transport/schema/semantic failures retain the deterministic verified response. |
| 37. GEMINI FINE-TUNING — DO THIS CORRECTLY | NOT STARTED | Cloud credentials/configuration absent; real integration still requires implementation. |
| 38. AI EVALUATION DATASET | IN PROGRESS | Machine-readable cases cover all eleven languages, nine intent families, multi-turn context and three fabrication attacks; coverage and deterministic adversarial checks pass. Live provider and native-speaker scoring remain. |
| 39. RAG / GROUNDING | IMPLEMENTED | Numerical answers use typed structured grounding. Approved-document retrieval metadata and authority rules are documented; no vector database is added without an allowlisted corpus. |
| 40. TWO LANGUAGE PROVIDERS | IN PROGRESS | BHASHINI pipeline and Google Cloud Translation adapters plus ordered original-text fallback are fixture-tested; live credentials are absent. |
| 41. LANGUAGE CAPABILITY MATRIX | IMPLEMENTED | All eleven UI languages package all **170/170** strings. Deterministic chat drafts exist for all 11 and preserve °C / % / numbers. BHASHINI/Google still unused without credentials (`language_provider: original/deterministic`). Native-speaker review remains. |
| 42. VOICE-FIRST EXPERIENCE | IMPLEMENTED / UNVERIFIED ON DEVICE | Android speech intent and TTS wired. Emulator launched Google Speech (Bangla). Spoken transcript send and heard TTS words UNVERIFIED. Cloud voice 501. |
| 43. OFFLINE-FIRST ANDROID ARCHITECTURE | TESTED / VERIFIED ON DEVICE | Room-backed repository. Airplane-mode + force-stop relaunch showed cached forecast and offline chat. |
| 44. ROOM ENTITIES | IMPLEMENTED | Weather, chat, saved places (+purpose), sync metadata, notification receipts, alert rules (Room v7). ForecastSync reads `alertRulesOnce` before posting. `deleteAlertRule` runs when a channel is turned off; deleting a place deletes its rules. JVM tests cover allow/block/duplicate. Live official-alert notification via a saved rule is UNVERIFIED ON DEVICE. |
| 45. OFFLINE WEATHER BUNDLE | TESTED | The compact gzip-capable bundle includes forecast, alerts, scores, provenance and freshness. Backend ETag/304 behavior is tested; Android persists validators and weather transactionally in Room and avoids rewriting unchanged bundles. |
| 46. CACHE FRESHNESS | TESTED | Weather, official-alert and climate freshness windows plus expiry handling have JVM coverage and stale UI messaging. |
| 47. OFFLINE CHATBOT | TESTED / VERIFIED ON DEVICE | Local deterministic multilingual answers. Emulator airplane-mode + reverse-removed + kill/relaunch used cached numbers with an offline banner. |
| 48. LOW-CONNECTIVITY MODE | TESTED | User-visible Low Data Mode requests a three-day bundle and refreshes every twelve hours; normal mode requests seven days every six hours. Compression, ETags, manual refresh, timeouts, backoff and Wi-Fi-only sync remain active. |
| 49. OFFLINE ALERT REALITY | TESTED | Cached official headline, instructions and expiry remain available to offline chat. New alerts still require connectivity. |
| 50. BACKGROUND SYNCHRONIZATION | IMPLEMENTED / UNVERIFIED ON DEVICE | WorkManager six-hour refresh with constraints and backoff. Periodic fire not observed on device. |
| 51. NOTIFICATIONS | IMPLEMENTED | Two local channels (`official_warnings`, `local_risks`), permission, contentIntent, Room receipts, DEMO warning. No unused daily-briefing channel. FCM CREDENTIAL-BLOCKED. Shade tap UNVERIFIED; DEMO post VERIFIED ON DEVICE. Saved Room rules gate ForecastSync in this APK. |
| 52. RED ALERT EXPERIENCE | IN PROGRESS | Official cards map minor, moderate, and severe/extreme levels to high-contrast yellow, orange, and red states; Listen reads the headline and instruction. Device screen-reader test remains. |
| 53. OPTIONAL SMS DELIVERY | IN PROGRESS | Disabled SMS provider stub is listed on `/v1/capabilities` as `alert_delivery` status `disabled`; nothing in the request path sends SMS. Live SMS needs `SMS_*` credentials. |
| 54. CLIMATE AND HISTORICAL INFORMATION | TESTED | ERA5 2–30 year temperature/rainfall analysis includes annual values, completeness, OLS trend, anomaly, method, provenance and limitations. |
| 55. HOME SCREEN | IMPLEMENTED | Home shows Ask WeatherGPT, intro, score, metrics, advice, download, an alerts honesty block (active card / none active / unknown), and the first WeatherGPT risk estimate when present. |
| 56. FORECAST SCREEN | IN PROGRESS | Daily summaries, 72-hour detail, feels-like, humidity, gust, visibility, UV, source confidence and uncertainty explanation are shown from the fused bundle hour fields. |
| 57. ALERT CENTER | IMPLEMENTED | Branches on official_status. Local CAP feed live when URL configured. IMD **forecast** integration remains CREDENTIAL-BLOCKED. |
| 58. CHAT HISTORY | IN PROGRESS | Persisted messages and conversation browser; device interaction verification remains. |
| 59. SMART SUGGESTIONS | IN PROGRESS | Empty chat shows profile chips (farming spray, fishing waves, research climate, otherwise next hours). After an answer, hourly/warnings/score chips send those questions. Post-answer ranking remains. |
| 60. UI ACCESSIBILITY | IN PROGRESS | Large targets, icon labels, headings, assertive official alerts, scalable text and themed contrast. TalkBack reading order and data-heavy 200%-text screens still require review. |
| 61. BACKEND API | IN PROGRESS | Health, ready, capabilities (including disabled `alert_delivery`), providers, place search, GET/POST resolve and bundle, focused weather routes, marine (+ alias), climate, chat, translate, voice (501), device register/revoke and authenticated subscriptions. |
| 62. API RESPONSE CONTRACT | TESTED | Weather metadata and validation, caught-service, and unexpected-error envelopes include request IDs and retryability. |
| 63. ANDROID/BACKEND CONTRACT-FIRST DEVELOPMENT | IN PROGRESS | Shared weather-bundle, chat-answer and error examples are validated by backend models and Android DTOs. Broader generated-schema drift checking remains. |
| 64. LOCAL DEVELOPMENT NETWORKING | IMPLEMENTED / VERIFIED ON DEVICE | Emulator used `adb reverse` + `http://127.0.0.1:8000/`. LAN URL still supported. |
| 65. SECRETS | IMPLEMENTED | Root .env.example placeholders (including FIREBASE_*/SMS_*); .env and local secrets ignored. |
| 66. SECURITY | TESTED | Device-token subscription auth, rate-limit LRU, CAP/BHASHINI HTTPS allowlists, sanitized errors, security headers, Gemini budget/redaction, POST location bodies. |
| 67. PRIVACY | TESTED | Coarse-only Android location, no background GPS, backend-only provider calls, public_location for chat context, audit logs omit coordinates, Clear data remains. Room encryption deferred (documented residual risk). |
| 68. DEMO MODE | SKIPPED | User override of master spec §§68–69. Not required for this fork. Settings **DEMO warning** is a labelled simulated notification, not Demo Mode weather. |
| 69. DEMO DATA ARCHITECTURE | SKIPPED | Same override. No demo weather payloads. |
| 70. FAILURE HANDLING | IN PROGRESS | Provider partial/all-failure, malformed data, Gemini and language-provider fallback, internet loss, empty/stale Room cache and unavailable alert sources degrade explicitly; location permission grant/deny both exist, deny path UNVERIFIED ON DEVICE this pass. |
| 71. TESTING — BACKEND | TESTED | **174** pytest cases passed (2026-09-11 dead-code pass). |
| 72. TESTING — ANDROID | TESTED | `testDebugUnitTest` **52 passed** (`OfflineTest` + `NetworkTest`). Emulator journey Pixel_10a / API 37. No instrumentation tests. APK rebuilt this pass. |
| 73. END-TO-END DEMO TEST | SKIPPED | Master-spec Demo Mode skipped. The SIH emulator walkthrough in `docs/EVALUATION.md` is **not** Demo Mode. |
| 74. PERFORMANCE / SIH EVALUATION | IN PROGRESS | Earlier local latency samples recorded; not claimed as production benchmarks. Multilingual, device/offline and field evaluation remain. |
| 75. LOGGING / OBSERVABILITY | IN PROGRESS | Safe request ID, method/path/status/duration, provider latency/status, cache hit/miss, all-provider failure and fusion summaries are logged without query/chat/location content; production metrics backend remains. |
| 76. DOCUMENTATION | IN PROGRESS | Core documentation updated for security hardening and API surface; specialist docs pending. |
| 77. DEVELOPMENT SCRIPTS | IN PROGRESS | Windows setup, run, test and Android build scripts. |
| 78. OPTIONAL DOCKER | IMPLEMENTED | Optional backend Dockerfile and Compose service exist; Docker is absent locally, so container execution is unverified. |
| 79. CI | IN PROGRESS | GitHub Actions configured for backend and Android jobs without production secrets; re-verify after current changes. |
| 80. BUILD MILESTONES | IN PROGRESS | Environment, backend, Android build, cache, provider, fusion, chat, security and emulator-launch milestones are recorded; credential-dependent integrations remain. |
| 81. BUILD FAILURE RULE | IMPLEMENTED | Failures are recorded as blockers and feasible work continues. |
| 82. NO FAKE IMPLEMENTATIONS | IMPLEMENTED | No demo weather or invented fallback values are served; missing validated data remains unavailable. |
| 83. EXTERNAL CREDENTIAL BLOCKERS | IMPLEMENTED | Missing IMD, Gemini, BHASHINI, Google Translation, FCM and SMS credentials are explicitly documented and do not block credential-free services. |
| 84. UI STATES | IN PROGRESS | Loading, loaded, refreshing, offline/stale, empty, partial and error notices exist. |
| 85. FINAL REPOSITORY AUDIT | IMPLEMENTED | Independent audit + remediation 2026-09-11; dead-code pass the same day. Localization **11 × 170/170**, contrast min **6.37:1**. Verdict: **READY WITH MINOR NON-DEMO ISSUES** at **82 %**. |
| 86. REQUIRED VERIFICATION COMMANDS | IMPLEMENTED | Backend pytest **174**; Android unit tests **52** + `assembleDebug` + `lintDebug` passed 2026-09-11 dead-code pass. APK rebuilt. |
| 87. FINAL ACCEPTANCE CRITERIA | IN PROGRESS | Checklist below. Credential-blocked items stay open. Demo Mode is not required. |
| 88. SIH DEMONSTRATION STORY | IMPLEMENTED / UNVERIFIED ON DEVICE | Story path in EVALUATION.md. Emulator walkthrough ran; spoken voice turn unfinished. Demo Mode skipped. |
| 89. PRODUCT DIFFERENTIATOR | IN PROGRESS | Multi-source fusion, explainable confidence, chat-first offline and official-alert precedence are implemented in foundation form. |
| 90. MOST IMPORTANT FINAL RULE | IMPLEMENTED | Do not claim live IMD/Gemini/BHASHINI/FCM/SMS without credentials; do not invent weather. |
| 91. FINAL CODEX BEHAVIOUR | IMPLEMENTED | Persistent instructions followed; blockers recorded honestly. |

Theme contrast: all fourteen text/background pairs across both palettes pass 4.5:1, minimum **6.37:1** (measured 2026-09-11 by `scripts/check_accessibility.py`, which had been crashing with `StopIteration` until the audit repaired it; the earlier eight-pair 6.60:1 figure is superseded).

### Section 87 — acceptance checklist (IN PROGRESS)

**Met (credential-free / already verified in prior or current foundation work)**
- [x] Fresh setup is documented (README + scripts).
- [x] Backend starts (`scripts/run_backend.ps1`).
- [x] `/health` works; `/ready` reports readiness flags.
- [x] Chat is the primary interaction interface.
- [x] Text chat works (deterministic verified pipeline).
- [x] Multi-turn context works (conversation state).
- [x] Weather tools work for implemented forecast/alerts/score/climate/marine/compare paths (12 registry tools reachable from production chat).
- [x] Four **adapters** exist (Open-Meteo, OpenWeather, WeatherAPI, IMD probe) **plus** ECMWF IFS. Four **live model sources** were fused (Open-Meteo, OpenWeather, WeatherAPI, ECMWF). IMD forecasts remain CREDENTIAL-BLOCKED / probe-only — not a fourth live agency feed.
- [x] Open-Meteo integration exists and has been live-tested.
- [x] OpenWeather / WeatherAPI adapters exist (activate only with keys).
- [x] NWP/ECMWF architecture exists (IFS via Open-Meteo, fused separately).
- [x] Provider data is normalized before Android.
- [x] Fusion engine works; source disagreement handled; confidence explainable.
- [x] Weather Score works; occupation-specific recommendations exist for core profiles, with trace fields and hedge language (not certainty).
- [x] WeatherGPT Risk Estimates are distinguished from official alerts.
- [x] CAP architecture exists (parser/tests); unavailable never means no warning.
- [x] Red alert UI mapping exists.
- [x] Gemini works only through backend; cannot invent weather numbers; outage fallback works; disabled without credentials.
- [x] BHASHINI + second language provider adapters exist (fixture-tested).
- [x] Room is source of truth for cached weather/chat.
- [x] Forecast works offline from cache; offline chat answers cached-weather questions; stale labelled.
- [x] Low-connectivity download policy exists.
- [x] Climate/historical query works (ERA5).
- [x] Provider failure fallback works.
- [x] Documentation exists; no production secrets committed.
- [x] 11 UI languages exist with full string packs (**170/170** each).
- [x] Demo Mode **skipped by user override** (not required for this fork).

**Blocked / still open**
- [x] Android builds / debug APK — `app-debug.apk` 19.89 MB.
- [x] Android communicates with backend — emulator via `adb reverse` to `http://127.0.0.1:8000/`.
- [x] Onboarding, occupation, location — Hindi → Farming → Delhi exercised on emulator.
- [ ] IMD integration complete (normalized live forecasts) — credentials + mapping blocked.
- [ ] Specialist INCOIS official path — not live; model marine only.
- [ ] Official alerts authoritative from a trusted live feed — CAP URL works; IMD station forecasts still probe-only.
- [x] Local DEMO notification on emulator — FCM still needs `FIREBASE_*`.
- [ ] SMS delivery — needs `SMS_*`.
- [ ] Gemini live tool-calling / fine-tune pipeline — not started; chat tools are deterministic.
- [ ] BHASHINI / Google Translation live — credentials absent.
- [ ] Voice — Google Speech UI launched; spoken question and heard TTS words not completed; cloud voice 501.
- [x] Tests pass — backend **174 passed**; Android **52** unit tests. `assembleDebug`/`lintDebug` passed 2026-09-11 dead-code pass; APK rebuilt (19.86 MB).
- [ ] Full section-87 “complete” claim — blocked until remaining credential items clear.

## Next work
1. Finish a spoken voice question on the emulator and confirm TTS audio.
2. Point the Gradle wrapper at the official distribution when the network allows.
3. Add instrumentation tests; confirm CI on GitHub.
4. Supply BHASHINI / IMD / FCM / SMS credentials only when available — do not invent fallbacks.

Theme implementation: light, dark and system preference saved in DataStore. Voice capture uses Android recognizer activity and transcript confirmation; playback uses installed TTS. Cloud voice remains deliberately disabled (501) until configured. Google Speech UI was launched on the emulator; a spoken question was not completed.
