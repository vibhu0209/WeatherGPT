# WeatherGPT

Native Android weather companion with a **chat-first** interface. Everything lives in **D:\WeatherGPT**. The old nested `WeatherGPT` folder is not the application root.

## Problem

People need trustworthy local weather guidance in their language — especially for farming, fishing and outdoor work — without inventing numbers, hiding missing official warnings, or requiring an always-online experience.

## Solution

WeatherGPT fuses validated multi-provider forecasts on a FastAPI backend, answers in plain language through chat, keeps Room as the Android source of truth offline, and always separates **official warnings** from WeatherGPT risk estimates. Missing official data is reported as unavailable — never as “no warnings.”

## Why chatbot-first

Chat is the default screen: suggested questions, typing, or Speak → confirm transcript → send. Answers lead with a plain summary; an expandable evidence control shows sources, confidence reasons and update time. Forecast, alerts, home score and settings remain available, but conversation is the front door.
z
## Architecture

```
Android (Compose + Room + DataStore + WorkManager)
        │  HTTPS / LAN / emulator URL
FastAPI backend (validation, fusion, alerts, chat, translate)
        │
Open-Meteo (+ IFS) · OpenWeather* · WeatherAPI* · IMD probe*
        · CAP feed* · Open-Meteo Marine · ERA5 climate
        · Gemini* · BHASHINI* · Google Translate* · FCM*/SMS*
```

\* Requires credentials; disabled or probe-only without them. No weather API keys in the APK.

## Features

- Chat-first Q&A over verified weather tools (current, hourly, daily, alerts, score, climate, marine)
- Multi-model fusion with explainable confidence (uncalibrated; not a probability)
- Official CAP path when configured; local risk estimates always labelled separately
- 11 UI languages with full string packs (126/126); offline deterministic drafts English/Hindi-first
- On-device voice input/playback where the phone supports it; cloud voice endpoints return 501 until configured
- Offline Room cache, stale labelling, Low Data Mode, Wi-Fi-preferring background sync
- Light / dark / system theme, larger text, large labelled controls
- Device-token authenticated alert subscriptions (no IDOR listing of other devices’ coordinates)

## Tech stack

| Layer | Stack |
|---|---|
| Android | Kotlin, Jetpack Compose, Room, DataStore, WorkManager |
| Backend | Python FastAPI, httpx, Pydantic settings |
| Data | Open-Meteo (forecast, geocoding, marine, ERA5); optional OpenWeather, WeatherAPI, IMD, CAP |
| Optional AI / language | Gemini (wording only), BHASHINI, Google Cloud Translation |
| Optional delivery | FCM, SMS (stubs until credentials) |

## Setup

```powershell
cd D:\WeatherGPT
.\scripts\setup_backend.ps1 -Python <path-to-python-3.11-or-newer>
.\scripts\run_backend.ps1
```

Open http://localhost:8000/docs. Open-Meteo works without a key. No demonstration weather is served.

Open **D:\WeatherGPT\android** in Android Studio (SDK API 37.0 / build-tools 36.0.0 / AGP 9.1.1). Build with `scripts/build_android.ps1`. The Gradle wrapper uses the checked local distribution under `.tools\` when present.

- Emulator API base: `http://10.0.2.2:8000/`
- Physical device on same LAN: Settings → Connection settings → e.g. `http://192.168.1.10:8000/` (trailing `/` required)
- Release builds need a real HTTPS backend URL before distribution

CI runs backend and Android jobs without production secrets. Run `scripts/audit_repository.ps1` before release.

### One-click SIH local run

```powershell
powershell -ExecutionPolicy Bypass -File D:\WeatherGPT\scripts\run_sih.ps1
```

Starts the backend on `:8000`, boots `Pixel_10a` if needed, installs the debug APK, and launches WeatherGPT. Emulator uses `http://10.0.2.2:8000/`.

## Environment variables

Copy `.env.example` to `.env` at the repo root. Empty values disable optional integrations.

| Variable | Role |
|---|---|
| `OPENWEATHER_API_KEY` / `WEATHERAPI_KEY` | Extra forecast providers |
| `IMD_ENABLED` | IMD access probe (default false; not a completed live fourth provider) |
| `CAP_ALERT_URL` / `CAP_ALERT_ALLOWED_HOSTS` | Trusted official CAP feed |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Optional backend-only wording |
| `BHASHINI_*` / `GOOGLE_TRANSLATE_API_KEY` | Optional translation |
| `FIREBASE_*` | Optional FCM push (placeholders; empty = disabled) |
| `SMS_*` | Optional SMS delivery (placeholders; empty = disabled) |
| `CORS_ORIGINS` / `REDIS_URL` | Optional CORS and cache backend |

Do not commit `.env`. Do not put secrets in Android.

## Offline

Saved forecasts and messages live in Room; preferences in DataStore. Offline answers use the saved forecast and carry a stale warning. New official warnings cannot arrive without connectivity. Low Data Mode shortens the bundle and lengthens refresh. Use Settings → Clear data to wipe local state.

## Known limitations

- **No demo mode** (user override of master spec §§68–69). Real providers or clear unavailability only.
- IMD is probe/mapping-incomplete — do not count it as a live completed fourth integration.
- INCOIS official marine feed is not live; Open-Meteo Marine is model sea state only.
- Gemini, BHASHINI, Google Translation, FCM and SMS are not live without credentials.
- CAP parser is tested; a trusted live feed URL is still required for authoritative push of official alerts.
- Provider consensus confidence is uncalibrated, not a safety score.
- Device checklist (voice, TalkBack reading order, airplane mode, notification delivery) remains open — see `docs/EVALUATION.md` and `docs/IMPLEMENTATION_STATUS.md`.

## Further reading

- `docs/MASTER_SPEC.md` — original requirements
- `docs/IMPLEMENTATION_STATUS.md` — section-by-section status and §87 checklist
- `docs/API.md` — HTTP surface
- `docs/SECURITY.md`, `docs/PRIVACY.md`, `docs/SCALABILITY.md`, `docs/THREAT_MODEL.md`
- `docs/DATA_SOURCES.md`, `docs/LANGUAGE_SUPPORT.md`
