# WeatherGPT

Native Android weather companion with a **chat-first** interface. Everything lives in **D:\WeatherGPT**. The old nested `WeatherGPT` folder is not the application root.

## Problem

People need trustworthy local weather guidance in their language — especially for farming, fishing and outdoor work — without inventing numbers, hiding missing official warnings, or requiring an always-online experience.

## Solution

WeatherGPT fuses validated multi-provider forecasts on a FastAPI backend, answers in plain language through chat, keeps Room as the Android source of truth offline, and always separates **official warnings** from WeatherGPT risk estimates. Missing official data is reported as unavailable — never as “no warnings.”

**Authority path:** multi-model fusion is practical guidance for the SIH demo. The stack is built so **official IMD** (forecasts + warnings) becomes the primary authority layer once access is provisioned after selection — not endless “uncertain” hedging.

## Why chatbot-first

Chat is the default screen: suggested questions, typing, or Speak → confirm transcript → send. Answers lead with a plain summary; an expandable evidence control shows sources, confidence reasons and update time. Forecast, alerts, home score and settings remain available, but conversation is the front door.

## Architecture

```
Android (Compose + Room + DataStore + WorkManager)
        │  HTTPS / LAN / emulator URL
FastAPI backend (validation, fusion, alerts, chat, translate)
        │
Open-Meteo (+ IFS) · OpenWeather* · WeatherAPI* · IMD probe*
        · CAP feed* · Open-Meteo Marine · ERA5 climate
        · Groq* · BHASHINI* · Google Translate* · FCM*/SMS*
```

\* Requires credentials; disabled or probe-only without them. No weather API keys in the APK.

## Features

- Chat-first Q&A over verified weather tools (current, hourly, daily, alerts, score, climate, marine)
- Multi-model fusion with explainable confidence (uncalibrated; not a probability)
- Official CAP path when configured; local risk estimates always labelled separately
- 11 UI languages with full string packs (**170/170**); deterministic chat drafts in all 11; BHASHINI/Google Translation stay off without credentials
- On-device voice input/playback where the phone supports it; cloud voice endpoints return 501 until configured
- Offline Room cache, stale labelling, Low Data Mode, Wi-Fi-preferring background sync
- Full-screen onboarding: language → occupation → location (theme and large text are set automatically; notification permission is requested in Settings)
- Light / dark / system theme, larger text, large labelled controls
- Device-token authenticated alert subscriptions (no IDOR listing of other devices’ coordinates; re-registering a live device id is refused with 409)

## Tech stack

| Layer | Stack |
|---|---|
| Android | Kotlin, Jetpack Compose, Room, DataStore, WorkManager |
| Backend | Python FastAPI, httpx, Pydantic settings |
| Data | Open-Meteo (forecast, geocoding, marine, ERA5); optional OpenWeather, WeatherAPI, IMD, CAP |
| Optional AI / language | Groq (conversational tool orchestration; facts from WeatherGPT tools only), BHASHINI, Google Cloud Translation |
| Optional delivery | FCM, SMS (stubs until credentials) |

## Setup

```powershell
cd D:\WeatherGPT
.\scripts\setup_backend.ps1 -Python <path-to-python-3.11-or-newer>
.\scripts\run_backend.ps1
```

Open http://localhost:8000/docs. Open-Meteo works without a key. No demonstration weather is served.

Open **D:\WeatherGPT\android** in Android Studio (SDK API 37.0 / build-tools 36.0.0 / AGP 9.1.1). Build with `scripts/build_android.ps1`. The Gradle wrapper uses the checked local distribution under `.tools\` when present.

- Emulator API base: `http://10.0.2.2:8000/` (`localhost` inside the emulator is the emulator itself, not Windows)
- If the emulator cannot reach `10.0.2.2` (Windows Firewall often blocks `python.exe`), run `adb reverse tcp:8000 tcp:8000` and set the app URL to `http://127.0.0.1:8000/`
- Physical device on the same LAN: Settings → Connection settings → `http://<PC-IPv4>:8000/` (trailing `/` required). Find the PC address with `ipconfig` → IPv4. The backend must bind `0.0.0.0:8000` (`scripts/run_backend.ps1` already does).
- Override at build time: `gradlew installDebug -Pweathergpt.apiUrl=http://192.168.1.10:8000/` or set `weathergpt.apiUrl` in `local.properties`
- Release builds need a real HTTPS backend URL before distribution

CI runs backend and Android jobs without production secrets. Run `scripts/audit_repository.ps1` before release.

### One-click SIH local run

```powershell
powershell -ExecutionPolicy Bypass -File D:\WeatherGPT\scripts\run_sih.ps1
```

Starts the backend on `0.0.0.0:8000`, boots `Pixel_10a` if needed, installs the debug APK, and launches WeatherGPT. Uses `http://10.0.2.2:8000/` when that route works; otherwise `adb reverse` plus `http://127.0.0.1:8000/` so Windows Firewall does not have to be opened.

## Environment variables

Copy `.env.example` to `.env` at the repo root. Empty values disable optional integrations.

| Variable | Role |
|---|---|
| `OPENWEATHER_API_KEY` / `WEATHERAPI_KEY` | Extra forecast providers |
| `IMD_ENABLED` | IMD access probe (default false; not a completed live fourth provider) |
| `CAP_ALERT_URL` / `CAP_ALERT_ALLOWED_HOSTS` | Trusted official CAP feed |
| `GROQ_API_KEY` / `GROQ_MODEL` | Backend-only conversational orchestration (OpenAI-compatible tool calling). Facts remain tool-grounded. Deterministic chat is the fallback when Groq is unavailable. |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Legacy / unused by active runtime (kept for older env files). |
| `BHASHINI_*` / `GOOGLE_TRANSLATE_API_KEY` | Optional translation |
| `GOOGLE_PLACES_ENABLED` | Default `false` (zero-cost). Set `true` only if you intentionally use paid Google Places/Geocoding. |
| `GOOGLE_PLACES_API_KEY` | Optional; used only when `GOOGLE_PLACES_ENABLED=true`. Alias: `GOOGLE_MAPS_API_KEY`. Without Google, Open-Meteo + popular cities (and optional Mappls) still work. |
| `MAPPLS_ACCESS_TOKEN` | Optional MapmyIndia / Mappls search |
| `FIREBASE_*` | Optional FCM push (placeholders; empty = disabled) |
| `SMS_*` | Optional SMS delivery (placeholders; empty = disabled) |
| `CORS_ORIGINS` / `REDIS_URL` | Optional CORS and cache backend |

Do not commit `.env`. Do not put secrets in Android.

### Google Places API key (optional / paid — off by default)

Place search works with **₹0 Maps spend** via Open-Meteo geocoding + popular cities (and optional Mappls if you have a free/usable token). Google Places remains in the codebase but is **disabled** unless you set:

```
GOOGLE_PLACES_ENABLED=true
GOOGLE_PLACES_API_KEY=...
```

If Google returns `REQUEST_DENIED` (for example billing disabled), WeatherGPT falls back immediately, applies a long cooldown, and does not retry Google on every keystroke. Users still see location results from free providers.

Capabilities expose only `google_places_configured` and `google_places_enabled` — never the key.

To enable Google later (billing required by Google Cloud):

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project (or pick an existing one).
2. Link a **billing account**.
3. Enable **Places API** (classic Autocomplete + Place Details) and **Geocoding API**.
4. Create an API key; restrict it to Places + Geocoding; optionally IP-restrict to your backend.
5. Set `GOOGLE_PLACES_ENABLED=true` and `GOOGLE_PLACES_API_KEY=...` in repo-root `.env`, then restart the backend.

Docs: [Get a Places API key](https://developers.google.com/maps/documentation/places/web-service/get-api-key) · [Maps pricing / free usage](https://developers.google.com/maps/billing-and-pricing/overview)

## Offline

Saved forecasts and messages live in Room; preferences in DataStore. Offline answers use the saved forecast and carry a stale warning. New official warnings cannot arrive without connectivity. Low Data Mode shortens the bundle and lengthens refresh. Use Settings → Clear data to wipe local state.

## Known limitations

- **No Demo Mode** (user override of master spec §§68–69). Real providers or clear unavailability only. Settings can post a labelled **DEMO warning** notification; that is not demo weather.
- **Adapters vs live providers:** Open-Meteo, OpenWeather, WeatherAPI and ECMWF IFS were live-fused here. IMD **forecasts** are a probe only — not a completed fourth live agency provider. IMD **CAP warnings** work when `CAP_ALERT_URL` is configured.
- INCOIS official marine feed is not live; Open-Meteo Marine is model sea state only.
- BHASHINI, Google Translation, FCM and SMS are not live without credentials. Groq powers online conversational reasoning and tool orchestration; meteorological facts stay grounded in deterministic WeatherGPT tools. When Groq is unavailable or the device is offline, WeatherGPT falls back to deterministic grounded responses.
- Provider consensus confidence is uncalibrated, not a safety score.
- Spoken voice turn, TalkBack reading order, notification-shade tap and WorkManager fire remain UNVERIFIED or PARTIAL — see `docs/EVALUATION.md`.
- Gradle wrapper may use a machine-local zip when the official distribution URL is unreachable.
- See `docs/FINAL_AUDIT.md`, `docs/REMAINING_WORK.md`, `docs/audit_status.json` and `docs/IMPLEMENTATION_STATUS.md` (must agree).

## Further reading

- `docs/MASTER_SPEC.md` — original requirements
- `docs/IMPLEMENTATION_STATUS.md` — section-by-section status and §87 checklist
- `docs/API.md` — HTTP surface
- `docs/SECURITY.md`, `docs/PRIVACY.md`, `docs/SCALABILITY.md`, `docs/THREAT_MODEL.md`
- `docs/DATA_SOURCES.md`, `docs/LANGUAGE_SUPPORT.md`
