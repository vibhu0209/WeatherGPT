# Verification and accessibility checklist

Demo Mode (master spec §§68–69) is **skipped by user override** and is not required for this fork.
A labelled **DEMO warning** notification in Settings is not Demo Mode weather.

## Automated results (2026-09-11 dead-code pass)

- Backend: **174** pytest passed.
- Android unit: **52** (`OfflineTest` 27 + `NetworkTest` 25), including alert-rule allow/block/dedup. `lintDebug` passed (0 errors, 35 warnings, 2 hints). `assembleDebug` produced `android/app/build/outputs/apk/debug/app-debug.apk` (19.86 MB) including Home/Forecast/chat wiring and alert-rule gating.
- Localization: **11 × 170/170**. Contrast: **14 pairs, min 6.37:1** (supersedes the older 6.60:1 / eight-pair figure).
- Live fusion (this environment, with keys): Open-Meteo, OpenWeather, WeatherAPI, ECMWF IFS — four **live model sources**. IMD forecasts remain a **probe**, not a fourth live agency provider. CAP warnings live when `CAP_ALERT_URL` is set.

## Emulator run (Pixel_10a, `sdk_gphone16k_x86_64`, API 37)

Installed debug APK via `adb reverse tcp:8000` and `http://127.0.0.1:8000/`.

| Check | Result |
|---|---|
| Fresh install / onboarding Hindi → Farming → Delhi | PASS |
| Language choice | PASS (Hindi, later Bengali) |
| Occupation | PASS (Farming, later Fishing) |
| Location permission granted | PASS (city pick; GPS deny not separately recorded) |
| Location permission denied | UNVERIFIED |
| Home | PASS |
| Chat text | PASS |
| Forecast + source disagreement | PASS (66/100, 4 sources) |
| Alerts screen | PASS (honest none-active + IMD link) |
| Saved locations add | PASS (Delhi, Mumbai) |
| Compare locations | PASS (Mumbai vs Delhi on screen) |
| Voice input | PARTIAL — Google Speech UI launched (Bangla); spoken question not sent |
| TTS | PARTIAL — Listen tapped; mixer ran; words not confirmed by ear |
| Notification permission / DEMO notification | PASS (labelled DEMO, not official weather) |
| Notification shade tap | UNVERIFIED (`contentIntent` / `open_tab=3` verified in code) |
| App restart + cached data | PASS |
| Offline: fetch → airplane + reverse remove → kill → relaunch | PASS |
| Offline banner + cached chat | PASS |
| Reconnect + refresh | PASS |
| TalkBack reading order | UNVERIFIED (older smoke test only) |
| WorkManager periodic fire | UNVERIFIED |

## Device checks still required

Do not present these as passed:

1. Location permission **denied** / GPS unavailable path.
2. Spoken voice question → transcript → send; heard TTS in the target language.
3. Physical notification-shade tap.
4. TalkBack spoken reading order on forecast/alerts.
5. Data-heavy screens at 200% text / landscape.
6. Rebuilding the APK after the alert-rule read-path (source is TESTED on JVM only).

No elderly-user or child usability study has been performed.
