# Verification and accessibility checklist

## Automated results
- Backend: 70 tests passed on 2026-09-09.
- Live fusion: the backend returned 161 hourly points from independent GFS and ECMWF IFS model families, reported disagreement, and produced explainable confidence 66/100. Official alerts correctly remained unavailable.
- Android: `assembleDebug`, `testDebugUnitTest`, and `lintDebug` passed on 2026-09-09. Ten JVM tests passed and the debug APK was installed on a Pixel_10a emulator.

- Local latency sample on 2026-09-09: first live two-model Delhi bundle 800.6 ms; immediate in-process cache hit 37.5 ms; provider calls reported Open-Meteo GFS 641 ms and ECMWF IFS 735 ms. This is one development-machine sample, not a production benchmark.
- Room v2-to-v3 emulator upgrade: the existing private database was upgraded in place; MainActivity resumed and the latest AndroidRuntime/Room log window contained no errors.
- Theme static verification: all eight explicit foreground/background pairs exceed WCAG 4.5:1 (minimum measured 6.60:1). Resource references resolve. This does not replace device visual testing.

## Device checks still required
The emulator verifies installation, clean launch, resumed activity and the eleven-language onboarding hierarchy. The following hands-on checks remain; do not present them as passed.
1. Fresh install: choose English/Hindi, test GPS allow/deny/unavailable paths, select a village/town manually, and download weather.
2. Toggle light/dark/system and larger text. Force-close and reopen; preferences persist.
3. Set phone text size to 200%; inspect every screen at narrow width and landscape.
4. Enable TalkBack. Verify reading order, labelled controls, selection state and touch targets.
5. Speak a question; review transcript; send; listen; test missing speech engine/language.
6. Restart without network. Downloaded forecast remains visible with timestamp. Ask tomorrow, then morning. Missing periods must show unavailable.
7. Disconnect with empty cache. No weather numbers appear.
8. Open warnings. It must say warnings are not connected, never “no warnings”. Open IMD link.
9. Clear chat. Clear all data with confirmation. Location, preferences and cache should disappear.
10. Wi-Fi-only background sync respects network constraints. WorkManager scheduling is not exact.

No elderly-user or child usability study has been performed. The current accessibility choices are large labelled controls, readable themed contrast, scrolling screens, scalable text and plain wording, not a claim of validated usability for every population.









