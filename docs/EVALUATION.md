# Verification and accessibility checklist

## Automated results
- Backend: 16 tests passed on 2026-09-06.
- Live Open-Meteo: full backend service returned 151 forecast points and one contributing provider. Official alerts correctly unavailable.
- Android: `assembleDebug` and `testDebugUnitTest` passed on 2026-09-07. The APK was generated successfully.

- Theme static verification: all eight explicit foreground/background pairs exceed WCAG 4.5:1 (minimum measured 6.60:1). Resource references resolve. This does not replace device visual testing.

## Device checks still required
No emulator/device has been used yet. Do not present these checks as passed.
1. Fresh install: choose English/Hindi, select village/town, download weather.
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
