# Verification and accessibility checklist

## Automated results
- Backend: 74 tests passed on 2026-09-09.
- Live fusion: the backend returned 161 hourly points from independent GFS and ECMWF IFS model families, reported disagreement, and produced explainable confidence 66/100. Official alerts correctly remained unavailable.
- Android: `assembleDebug`, `testDebugUnitTest`, and `lintDebug` passed on 2026-09-09. Twelve JVM tests passed and the debug APK was installed on a Pixel_10a emulator.

- Local latency sample on 2026-09-09: first live two-model Delhi bundle 800.6 ms; immediate in-process cache hit 37.5 ms; provider calls reported Open-Meteo GFS 641 ms and ECMWF IFS 735 ms. This is one development-machine sample, not a production benchmark.
- Room v2-to-v3 emulator upgrade: the existing private database was upgraded in place; MainActivity resumed and the latest AndroidRuntime/Room log window contained no errors.
- Conditional-download contract: backend ETag/304 behavior and Android rejection of 304 without matching local state are unit-tested. Room v4 adds validator/check timestamps; the existing emulator database upgraded and relaunched with no sampled Room, SQLite or runtime errors.
- Low Data Mode device check: the Hindi control and explanation rendered, selection persisted through force-stop/relaunch, and the test setting was restored. Unit tests verify three-day/12-hour low-data policy versus seven-day/6-hour normal policy.
- Theme static verification: all eight explicit foreground/background pairs exceed WCAG 4.5:1 (minimum measured 6.60:1). Resource references resolve.
- Theme device persistence: dark, light and system selections each remained checked after a force-stop and relaunch on the Pixel_10a emulator. Visual review at varied display sizes remains.
- Text scaling sample: the Hindi empty-chat screen was visually inspected at Android 200% font scale on 1080×2424. Its heading, body, location controls and five navigation labels remained visible without overlap; data-heavy screens remain unverified.
- Accessibility-service smoke test: installed TalkBack was enabled, WeatherGPT relaunched and remained the resumed activity, and no AndroidRuntime/WeatherGPT errors appeared in the sampled logs. TalkBack was then disabled. Spoken reading order was not verified.
- Voice prerequisites: the emulator resolves one speech-recognition activity and one Google TTS service. End-to-end capture and playback remain unverified.

## Device checks still required
The emulator verifies installation, clean launch, resumed activity and the eleven-language onboarding hierarchy. The following hands-on checks remain; do not present them as passed.
1. Fresh install: choose English/Hindi, test GPS allow/deny/unavailable paths, select a village/town manually, and download weather.
2. Theme and app larger-text preferences persist through relaunch. Inspect data-heavy screens with larger text enabled.
3. The Hindi empty-chat screen passed at 200% phone text size; inspect forecast, alerts, history and settings at narrow width and landscape.
4. TalkBack enable/relaunch smoke test passed. Verify spoken reading order, labelled controls, selection state and touch targets by listening.
5. Speak a question; review transcript; send; listen; test missing speech engine/language.
6. Restart without network. Downloaded forecast remains visible with timestamp. Ask tomorrow, then morning. Missing periods must show unavailable.
7. Disconnect with empty cache. No weather numbers appear.
8. Open warnings. It must say warnings are not connected, never “no warnings”. Open IMD link.
9. Clear chat. Clear all data with confirmation. Location, preferences and cache should disappear.
10. Wi-Fi-only background sync respects network constraints. WorkManager scheduling is not exact.

No elderly-user or child usability study has been performed. The current accessibility choices are large labelled controls, readable themed contrast, scrolling screens, scalable text and plain wording, not a claim of validated usability for every population.









