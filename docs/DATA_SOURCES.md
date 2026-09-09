# Data sources and research

Official documentation checked on 2026-09-06. Availability is verified only where explicitly stated.

| Provider | Implementation / authority | Access and coverage | Failure / freshness |
|---|---|---|---|
| [Open-Meteo](https://open-meteo.com/en/docs) | Live tested, global model forecast; not an official Indian warning | No-key development endpoint, GFS seamless, 7-day hourly request. Review commercial-use terms before deployment. Attribute Open-Meteo and model origin. | 10-second transport timeout, bounded retry, 15-minute cache; retained timestamp on stale fallback. |
| [Open-Meteo geocoding](https://open-meteo.com/en/docs/geocoding-api) | Place search | No-key name search; small villages may be missing. User chooses the result. | Explicit retry message; no invented coordinates. |
| [OpenWeather](https://openweathermap.org/forecast5) | Adapter implemented, not live tested | API key, supported 5-day / 3-hour product, temperature/wind/humidity. Quota and licensing depend on account. | Missing key disables it; incompatible precipitation interval excluded. |
| [WeatherAPI](https://www.weatherapi.com/docs/) | Adapter implemented, fixture-tested | API key, request 3 days, actual horizon depends on plan; temperature, rain, wind, humidity. Attribution and quotas depend on subscription. | Disabled without key. Partial provider failures do not break others. |
| [IMD](https://api.imd.gov.in/public/api_reference.html) | Official Indian authority; adapter probe-only until credentials and station mapping are complete — not a live normalized fourth forecast provider | Documented cityforecastloc, station mapping, current weather, warnings and specialist endpoints. Verify provisioned access. | Never substitutes general model data for an official warning. UI says warnings unavailable. |
| [INCOIS](https://incois.gov.in/) | Official ocean information feed **not live** | Operational feed/access and licensing still to confirm. Do not claim live INCOIS warnings. | Official marine warnings remain unavailable; model sea state uses Open-Meteo Marine instead. |
| [ECMWF IFS via Open-Meteo](https://open-meteo.com/en/docs/ecmwf-api) | Independent `ecmwf-ifs` model-family adapter, fixture-tested and live-tested | Credential-free IFS hourly endpoint; delivery is attributed to Open-Meteo and model origin to ECMWF. It is fused separately from the GFS family, never counted as a separate official-warning authority. | Same timeout/retry/validation path; model disagreement lowers confidence. |
| [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) | Live-tested deterministic climate summaries | ERA5 daily mean temperature or precipitation, 2–30 complete calendar years; reanalysis rather than a station observation. | Seven-day in-memory cache; incomplete years below 90% coverage excluded from trend. |
| [Open-Meteo Marine Weather API](https://open-meteo.com/en/docs/marine-weather-api) | Used for **model sea state** (fixture tests and live Arabian Sea request passed). Not a substitute for official INCOIS/IMD marine warnings. | Wave height/direction/period, swell and sea-surface temperature for a user-selected sea coordinate. Exposed as `/v1/marine/forecast` and alias `/v1/weather/marine`. | Coastal accuracy is limited and output is not suitable for navigation; IMD and INCOIS warnings take precedence when available. |

Additional implementation references:
- [Android offline-first architecture](https://developer.android.com/topic/architecture/data-layer/offline-first): Room local reads and WorkManager persistent synchronization.
- [AGP 9.1.1 compatibility](https://developer.android.com/build/releases/agp-9-1-0-release-notes): installed API 37.0 / build-tools 36.0.0 / Gradle 9.3.1.
- [KSP releases](https://github.com/google/ksp/releases): Room code generation compatibility.
- [BHASHINI compute](https://bhashini.gitbook.io/bhashini-apis/pipeline-compute-call): pipeline discovery and compute credentials still required; adapter is fixture-tested but not live-tested.
- [Gemini text generation](https://ai.google.dev/gemini-api/docs/text-generation) and [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output): optional backend-only wording pass with schema and semantic validation; disabled until both key and model are configured.

No demo mode, fixtures served to users, commercial API calls, or cloud training jobs. Test fixtures exist only in automated tests. SIH26068 metadata is taken from the user's specification; independent SIH listing verification remains outstanding.

