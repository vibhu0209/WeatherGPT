# WeatherGPT

A native Android weather companion with a chat-first interface for everyday users. Everything is in **D:\WeatherGPT**. The old nested `WeatherGPT` folder was already present and is not used.

## Run the backend

The repository-local Python environment is already prepared on this computer.

```powershell
cd D:\WeatherGPT
.\scripts\run_backend.ps1
```

Open http://localhost:8000/docs for the actual API. Open-Meteo works without a key; no demonstration weather is included.

For a new environment, use `scripts/setup_backend.ps1 -Python <path-to-python-3.11-or-newer>`.

## Android

Open **D:\WeatherGPT\android** in Android Studio. SDK API 37.0 and build tools 36.0.0 are used with AGP 9.1.1. Java is supplied by Android Studio. Build with `scripts/build_android.ps1`.

The verified debug APK is at `android/app/build/outputs/apk/debug/app-debug.apk`. No phone or emulator was connected during the build, so installation and visual/voice testing remain in the device checklist.

CI runs backend compilation/tests plus Android unit tests, lint, and debug assembly without production secrets. Test fixtures remain inside tests and are never served as app weather. Run `scripts/audit_repository.ps1` before release to scan tracked source for common secret formats and confirm `.env` remains ignored.

The Gradle wrapper uses the checked local distribution at `D:\WeatherGPT\.tools\gradle-9.3.1-bin.zip`. This avoids downloading Gradle through a proxy or unreliable connection. Keep the project at `D:\WeatherGPT`; if it is moved, update `distributionUrl` in `android\gradle\wrapper\gradle-wrapper.properties`.

The debug app uses `http://10.0.2.2:8000/` for an Android emulator. On a phone connected to the same Wi-Fi as this PC, go to Settings → Connection settings and enter the PC's LAN address, for example `http://192.168.1.10:8000/`. The backend must be running and Windows Firewall must allow the connection. The address must end with `/`.

Release builds require a real HTTPS backend URL; `https://localhost/` is deliberately a non-production default. Do not distribute the release configuration until it is changed.

## Everyday use

1. Choose a language and search for your village or town.
2. Tap a suggested question, type, or tap **Speak**. Review the speech transcript before sending.
3. Tap **Listen** below an answer. Voice availability depends on the speech engines installed on the phone.
4. Open **Weather** to download a forecast for later use.
5. In **Settings**, choose **Light**, **Dark**, or **Follow phone**, and optionally enable **Larger text**.
6. Optionally enable local WeatherGPT risk notifications. These are calculated forecast risks and are never presented as government warnings.

The **Home** screen now shows the current forecast, an explainable 24-hour Weather Score, limiting factors, and profile-sensitive advice. The Weather screen includes daily summaries followed by hourly detail. The score is deterministic and is always labelled as separate from official safety warnings.

Chat can also answer ten-year temperature and rainfall trend questions using deterministic ERA5 reanalysis calculations. Responses include period, trend, coverage, provenance and the limitation that a reanalysis grid cell may differ from a nearby station and cannot attribute climate causes.

Controls are at least 52–56 dp, labels accompany icons, text scales with phone settings, and screens scroll rather than requiring small fixed text. No account or GPS permission is required. Background refresh defaults to Wi-Fi only every six hours, subject to Android scheduling.

## What is verified

The Python backend tests and a real Open-Meteo weather request have passed. See `docs/IMPLEMENTATION_STATUS.md` for Android verification and outstanding features.

## Honest limitations

This is an initial working implementation, **not completion of the entire master specification**. English and Hindi cover the full core UI; nine other languages currently translate main controls only. Chat uses deterministic English/Hindi templates, not Gemini. IMD normalization, marine services, cloud translation and authoritative push delivery are not connected. CAP 1.2 ingestion is implemented and tested but requires a trusted live feed in `CAP_ALERT_URL`. The app reports unavailable official data clearly and links to IMD. Missing warning data is never interpreted as no warning.

OpenWeather and WeatherAPI adapters activate only when configured in the root `.env`. IMD's access adapter is disabled by default and cannot yet supply normalized weather. Do not count it as a completed fourth integration. Provider consensus is an uncalibrated median, not a claim of superior accuracy or a safety score.

Saved forecasts and messages live in Room; preferences live in DataStore. Offline answers use the saved forecast and carry a stale warning. New warnings cannot arrive without a connection. Use Settings to clear local data.

See `docs/MASTER_SPEC.md` for the original request. The user's latest instruction explicitly skips demo mode.
