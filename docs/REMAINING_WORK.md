# WeatherGPT — remaining work

Ordered P0 → P1 → P2 → optional. Companion to `docs/FINAL_AUDIT.md` (audit 2026-09-11).
Every item states the component, the exact problem, the files, the expected result and how to
verify. Items fixed during the audit are listed at the bottom so they are not redone.

Verified baseline after the 2026-09-11 dead-code pass: backend **174/174 pytest**, Android **52 unit
tests**, `assembleDebug` APK 19.86 MB (rebuilt this pass), `lintDebug` **green** (0 errors, 35 warnings), localization **11 × 170/170**,
contrast **14 pairs, min 6.37:1**, emulator **Pixel_10a / API 37** (earlier same-day journey; this pass did not re-run the emulator). Still open: P1-7, P1-9, P1-13, spoken voice, and the remaining P2 list.

---

## P0 — demo blockers

### [x] P0-1 — Verification: run the complete journey on an emulator or device
- **Component:** Android (end-to-end)
- **Problem:** Build, APK and unit tests pass, but no user journey has been observed. Onboarding,
  voice, notifications, WorkManager sync, TalkBack and airplane-mode offline are all
  🔵 UNVERIFIED. The largest single block of unproven functionality.
- **Files:** `scripts/run_sih.ps1`, `android/app/src/main/java/in/weathergpt/*`
- **Expected result:** A recorded pass/fail for each step: onboarding (language → occupation →
  location), chat text answer, Speak → transcript → send, TTS playback, alerts screen states,
  notification delivery and tap, airplane mode relaunch showing cached forecast with a stale
  label, offline chat answering from cache.
- **Verify:** `powershell -ExecutionPolicy Bypass -File D:\WeatherGPT\scripts\run_sih.ps1`, then
  walk each step and append results to `docs/EVALUATION.md` with the device/API level.

### [x] P0-2 — Gemini free-tier quota will degrade the live demo
- **Component:** AI / operations
- **Problem:** The configured key is free-tier. A live 429 was captured:
  `Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20`.
  Roughly twenty audit calls exhausted it; every later chat answer fell back to the deterministic
  template. The fallback is correct, but the demo's "conversational" claim will not show.
- **Files:** root `.env` (`GEMINI_API_KEY`, `GEMINI_MODEL`), `backend/app/ai.py`
- **Expected result:** Either a paid/raised quota, or a rehearsed script that presents the
  template fallback as the deliberate safety behaviour.
- **Done (mitigated, quota not raised):** `should_polish()` skips boilerplate-only drafts; 429
  opens a 300s circuit and never retries; 503/timeout cool down 60s. Deterministic answers remain
  the demo floor. Free-tier key can still exhaust if you force many polishable calls.
- **Verify:** Send 30 consecutive `/v1/chat/message` requests and confirm none of the answers
  regress to the raw `"Place · YYYY-MM-DD"` template; check the server log for no 429.

---

## P1 — important before SIH

### [x] P1-1 — Gemini rewording is rejected on the main forecast path
- **Component:** AI
- **Problem:** `finalize_chat` calls `polish()` on every chat request (~2 s latency and quota),
  but on the primary forecast template the candidate is rejected and the draft is returned. The
  draft's `"Pune · 2026-09-12"` header and `"18 to 30.5°C"` range make `validate_polish`'s exact
  number-set and number-unit-pair equality nearly impossible to satisfy after natural rewording.
  Isolated probes with a simpler draft were accepted, proving the path works.
- **Files:** `backend/app/chat.py` (draft construction), `backend/app/ai.py` (`polish`,
  `validate_polish`), `backend/app/main.py` (`finalize_chat`)
- **Expected result:** The AI pass measurably improves the main answer's wording while keeping
  the anti-hallucination guarantee. Recommended approach: keep the `"Place · date"` header out of
  the AI-visible draft and re-attach it afterwards, and/or pass structured per-field facts so the
  model has no reason to reformat ranges. **Do not relax `validate_polish`** — the number and
  severity equality checks are the core safety property.
- **Verify:** A new test asserting a reworded candidate for the standard forecast draft is
  accepted; plus the existing `test_ai.py` cases and the adversarial battery must still pass.

### [x] P1-2 — Compare-place picker missing in Android
- **Component:** Android
- **Problem:** `vm.setComparePlace()` is defined but called from nowhere (grep: one reference, the
  definition). `comparePlace` is therefore always `null`, `secondary_location` is never sent, and
  the working, tested backend compare path is unreachable from the app. `IMPLEMENTATION_STATUS`
  §30 claims this picker exists.
- **Files:** `android/app/src/main/java/in/weathergpt/WeatherViewModel.kt:41`,
  `MainActivity.kt` (`ChatScreen`, `PlaceDialog`), `backend/app/main.py:330`
- **Expected result:** A control in chat (or the place dialog) selects a second saved place;
  `ChatScreen`'s existing `comparePrefix` path then sends `secondary_location` and the answer
  compares two places.
- **Verify:** On device, pick a compare place, ask "compare rain tomorrow", and confirm the answer
  names both places; server log shows one `/v1/chat/message` with `secondary_location` present.

### [x] P1-3 — Notification tap opens nothing
- **Component:** Android notifications
- **Problem:** No `setContentIntent` on any notification, so tapping a severe-weather warning does
  nothing. Master-spec requirement "notification tap opens correct screen" is unmet.
- **Files:** `android/app/src/main/java/in/weathergpt/ForecastSync.kt` (both
  `NotificationCompat.Builder` sites, lines ~29 and ~80)
- **Expected result:** Tapping an official warning opens `MainActivity` on the Alerts tab; tapping
  a risk estimate opens the risk section. Use a `PendingIntent` with `FLAG_IMMUTABLE`.
- **Verify:** On device, trigger a notification, tap it, and confirm the correct tab opens from
  both cold and warm start.

### [x] P1-4 — Saved places cannot be deleted or re-purposed
- **Component:** Android / privacy
- **Problem:** `vm.deletePlace()` and `vm.updatePlacePurpose()` exist but no UI calls them. A user
  can only remove a saved location by wiping everything via "Clear data". Privacy requirement
  "saved locations can be deleted" is only met all-or-nothing.
- **Files:** `WeatherViewModel.kt:54` and `:147`, `MainActivity.kt` (`PlaceDialog` saved list,
  `SettingsScreen`)
- **Expected result:** Each saved place has a delete action and a purpose selector
  (Home/Farm/Harbour/Work) that updates the score profile via `purposeToProfile`.
- **Verify:** Add two places, delete one, confirm it disappears from Room and does not return
  after relaunch; change a purpose and confirm the Home score profile changes.

### [x] P1-5 — Chat bypasses the typed tool registry
- **Component:** Backend chat pipeline
- **Problem:** `TOOL_REGISTRY` (12 typed tools) is referenced only by tests. `main.py` keyword-
  branches for compare/marine/climate and imports `compare_locations` directly; the other ten
  tools are unreachable from chat. `IMPLEMENTATION_STATUS` §31 marks this "TESTED", which
  overstates it.
- **Files:** `backend/app/tools.py:204`, `backend/app/main.py` (`chat`), `backend/app/chat.py`
- **Expected result:** The chat pipeline resolves an intent and dispatches through
  `TOOL_REGISTRY`, so `get_weather_score`, `get_hourly_forecast`, `get_daily_forecast`,
  `get_active_alerts`, `get_provider_status`, `get_saved_locations`, `get_agromet_advisory` and
  `set_alert_rule` become reachable. Keep it deterministic; this is not a request to hand tool
  choice to the model.
- **Verify:** A test asserting each registry entry is reachable from `/v1/chat/message` for a
  representative question; existing chat tests must still pass.

### [x] P1-6 — Occupation barely affects chat answers
- **Component:** Chat / personalization
- **Problem:** Profile drives the Weather Score and recommendations (verified: 8 profiles → 8
  different scores) but inside a chat answer it only appends one farming spray line.
- **Files:** `backend/app/chat.py:78`, `backend/app/decision.py` (`recommendations`)
- **Expected result:** The answer includes the profile's top grounded recommendation from
  `recommendations()` so a fisherman, a farmer and a tourist get visibly different prose for the
  same weather.
- **Verify:** Test asserting the same location and weather yields different answer text for
  `profile=farming`, `fishing` and `tourism`.

### [ ] P1-7 — Gradle wrapper is not portable
- **Component:** Build / CI
- **Problem:** `distributionUrl=file\:///D\:/WeatherGPT/.tools/gradle-9.3.1-bin.zip` is an
  absolute local path to a **gitignored** file, so `./gradlew` cannot work on a fresh clone or a
  CI runner. CI currently sidesteps this with `gradle/actions/setup-gradle`.
- **Files:** `android/gradle/wrapper/gradle-wrapper.properties`
- **Expected result:** Point `distributionUrl` at the official
  `https://services.gradle.org/distributions/gradle-9.3.1-bin.zip` with its published
  `distributionSha256Sum`, optionally keeping the local path as a documented offline override.
- **Verify:** In a clean clone with an empty `GRADLE_USER_HOME`, `./gradlew assembleDebug`
  succeeds.

### [x] P1-8 — Android test coverage is one class
- **Component:** Android testing
- **Problem:** All 16 tests live in `OfflineTest.kt`. `Repository.refresh` (ETag/304 reuse,
  coordinate mismatch, temperature-range rejection), `WeatherViewModel` offline fallback,
  `ForecastSync` permission gating and Room migrations 1→7 are untested.
- **Files:** new tests under `android/app/src/test/java/in/weathergpt/`
- **Expected result:** Unit tests for `Repository.refresh` with a fake `Api`, for the
  `send()` catch-path falling back to `Offline.answer`, and for the `sources.isEmpty()` guard.
- **Verify:** `gradlew testDebugUnitTest` passes with a materially higher test count.

### [ ] P1-9 — No instrumentation tests exist
- **Component:** Android testing
- **Problem:** `testInstrumentationRunner` is configured but there is no `androidTest` source set,
  so navigation, Compose UI and real Room migrations are never exercised.
- **Files:** create `android/app/src/androidTest/java/in/weathergpt/`
- **Expected result:** At minimum a navigation smoke test (all five tabs render) and a Room
  migration test from v1 to v7 using `MigrationTestHelper`.
- **Verify:** `gradlew connectedDebugAndroidTest` passes on an emulator.

### [x] P1-10 — Shared state is process-local
- **Component:** Backend scalability
- **Problem:** Weather cache, CAP document cache, rate limiter, Gemini budget, device records and
  subscriptions all live in process memory. A restart drops every subscription; N workers multiply
  every limit by N. `RedisCacheBackend.__init__` raises by design.
- **Files:** `backend/app/cache.py` (`RedisCacheBackend`), `backend/app/subscriptions.py`,
  `backend/app/security.py` (`SlidingWindowLimiter`), `backend/app/ai.py` (`_calls`)
- **Expected result:** A working `RedisCacheBackend` selected when `REDIS_URL` is set, and
  subscriptions/devices persisted (SQLite now, PostgreSQL later) with hashed tokens.
- **Verify:** With `REDIS_URL` set, two backend workers share a cache hit and one rate-limit
  budget; subscriptions survive a restart.

### [x] P1-11 — Chat answers only reach en/hi
- **Component:** Multilingual
- **Problem:** `/v1/capabilities` reports `answer_languages: ["en","hi"]`. Nine languages need
  BHASHINI or Google Translate credentials (both empty). Separately, `validate_polish` is reused
  to gate translations, and its severity-word and protected-term equality checks will reject most
  genuine translations, so alert answers will fall back to English even **with** credentials.
- **Files:** `backend/app/main.py` (`finalize_chat`), `backend/app/ai.py` (`validate_polish`),
  `backend/app/language.py`
- **Expected result:** Credentials supplied, and a translation-specific validator that checks
  numbers and units (language-invariant) without requiring English severity words to survive
  translation.
- **Verify:** `POST /v1/chat/message` with `language=bn` returns Bengali with
  `language_provider` set, and an alert answer stays in Bengali rather than reverting to English.

### [x] P1-12 — Official warnings do not influence the Weather Score
- **Component:** Decision support
- **Problem:** An active severe official warning does not change the numeric score, so Home can
  read "Good conditions" beside a severe warning card. Not averaging warnings is correct, but the
  juxtaposition is misleading.
- **Files:** `backend/app/decision.py` (`weather_score`, `recommendations`),
  `backend/app/weather.py` (`_fetch_bundle` score assembly)
- **Expected result:** When an official warning is active, surface it as an explicit limiting
  factor and suppress a reassuring label, without folding the warning into the numeric penalty.
- **Verify:** Test that with an active severe warning the score payload carries an
  official-warning limiting factor and no "Good conditions" label.

### [ ] P1-13 — Confirm CI actually passes on GitHub
- **Component:** CI
- **Problem:** The Android job's exact command (`assembleDebug testDebugUnitTest lintDebug`)
  failed before this audit's lint fix, so the job was red. Remote runs cannot be confirmed from
  this environment, and the pinned action majors (`actions/checkout@v7`,
  `actions/setup-python@v7`, `actions/setup-java@v6`, `gradle/actions/setup-gradle@v6`) are
  unverified. The Android job also never runs `check_accessibility.py`.
- **Files:** `.github/workflows/ci.yml`
- **Expected result:** Both jobs green on a push, with `python scripts/check_accessibility.py`
  added alongside `check_localizations.py`.
- **Verify:** `gh run list` / `gh run watch` shows both jobs passing.

### [x] P1-14 — Reconcile documentation with verified reality
- **Component:** Documentation
- **Problem:** Nine concrete drift items are listed in `docs/FINAL_AUDIT.md` §4, including the
  onboarding step list (§23), the non-existent compare picker (§30), tools "TESTED" (§31), Gemini
  "not live-tested" (§33), string counts (171/126 vs actual 179), test counts (91/92 vs 102) and
  the contrast minimum (6.60:1 vs measured 6.37:1).
- **Files:** `docs/IMPLEMENTATION_STATUS.md`, `README.md`
- **Expected result:** Each claim matches observable behaviour, or is downgraded.
- **Verify:** Re-read both documents against the audit checklist; no claim exceeds its evidence.

---

## P2 — useful improvements

### [ ] P2-1 — Two-provider fusion has a systematic low bias
`weighted_median` returns the first value whose cumulative weight reaches the midpoint, so with
exactly two equal-weight providers it always returns the **lower** value rather than interpolating.
Fix in `backend/app/weather.py:40`; verify with a test asserting two providers at 20 °C and 30 °C
fuse to 25 °C. Matters whenever only Open-Meteo and ECMWF are configured.

### [ ] P2-2 — Fusion weights are uncalibrated
All weights in `backend/app/config/provider_weights.yaml` are equal. `backend/app/evaluation.py`
computes MAE/bias/RMSE/Brier but is used only by tests and never feeds weights. Collect
observations, then justify weights from measured skill. Verify by showing fused output shifting
toward the better-scoring provider.

### [ ] P2-3 — Forecast horizon does not affect confidence
`confidence_for` uses source count, coverage and disagreement but not lead time, so hour 1 and
hour 160 report the same confidence. Add a horizon term in `backend/app/weather.py:222`; verify
day-7 confidence is below day-1 for identical agreement.

### [x] P2-4 — No listen button on official alert cards
- **Done:** `OfficialAlertCard` has a Listen control; the Alerts tab passes `speak`. TTS still depends on the installed engine (UNVERIFIED ON DEVICE by ear).

### [x] P2-5 — `daily_forecast` notification channel is unused
- **Done:** The unused channel is no longer created. Only `official_warnings` and `local_risks` remain. There is still no daily briefing notification (not implemented; not faked).

### [ ] P2-6 — Route-level 404s bypass the error envelope
`DELETE /v1/alerts/subscriptions/<bad>` returns FastAPI's bare `{"detail":"Not Found"}` with no
`request_id`, contradicting §62. Add an `HTTPException`/404 handler in `backend/app/main.py`.
Verify that an unknown path returns `code`, `message`, `retryable` and `request_id`.

### [x] P2-7 — `tasks.py` and `delivery.py` are unreferenced
- **Done:** `backend/app/tasks.py` was unused and has been removed. `delivery.py` is imported by `/v1/capabilities` and reports FCM/SMS as `disabled`. Nothing in the request path sends cloud push or SMS; Android uses local notifications.

### [ ] P2-8 — `rule_store.py` is a separate backend store
`set_alert_rule` is reachable from chat and writes `backend/data/alert_rules.json` with an `owner` field (default `local`). That file is **not** the Android notification path — Room `AlertRule` + `ForecastSync` gates local notifications. Residual: the JSON store keeps precise coordinates and is not a multi-tenant device-isolated store.

### [x] P2-9 — Android alert rules are written but never read
- **Done:** `ForecastSync` and `CachedAlertReminder` call `alertRulesOnce`. Disabled channel deletes the row (`deleteAlertRule`); deleting a place deletes its rules. JVM tests cover allow, block, wrong place/channel, preference fallback, and duplicate suppression. Included in the 19.86 MB debug APK from this pass.

### [ ] P2-10 — Review the 35 lint warnings and the MissingTranslation suppression
`gradlew lintDebug` passes with **35 warnings** and 2 hints that have never been triaged, and
`build.gradle.kts:19` sets `lint { disable += "MissingTranslation" }`, which would mask genuine
translation gaps (currently none — `check_localizations.py` is the real gate). Triage the warnings
and document why the suppression is safe.

### [ ] P2-11 — `/ready` never reports not-ready
`/ready` always returns `status: ready` regardless of provider health, so an orchestrator can never
use it to pull a bad instance. Make it reflect at least one reachable weather provider. Verify by
forcing all providers to fail and seeing a non-ready response.

---

## Optional / future

- [ ] Gemini fine-tuning pipeline (`backend/ai/tuning/`) — correctly declared NOT STARTED; keep it
      that way until there is a real dataset and an explicit paid-training decision.
- [ ] INCOIS official marine feed and IMD normalized forecasts / nowcast / agromet text — all
      credential- and agreement-blocked; keep them honestly unavailable rather than approximated.
- [ ] FCM and SMS delivery — real provider integration, not the disabled shapes.
- [ ] Vector-store RAG for approved advisory documents — only with an allowlisted corpus.
- [ ] Split `MainActivity.kt` (596 lines, 10 screens) into per-screen files and introduce DI.
- [ ] App icon and a themed launch background (the manifest currently hardcodes
      `@android:style/Theme.Material.Light.NoActionBar`, which flashes light in dark mode).
- [ ] Replace the release `API_URL` placeholder `https://localhost/` before any distribution.
- [ ] Load test proving cache, coalescing and provider limits under many distinct grid cells.

---

## Already fixed in the 2026-09-11 audit — do not redo

| # | Was | Now |
|---|---|---|
| F1 | **P0** `POST /v1/device/register` let an unauthenticated caller claim an existing `device_id`, rotating the owner's token and **deleting their severe-weather subscriptions** (reproduced live) | Returns 409 for a live id; revoked ids reclaimable without inheriting subscriptions. 2 regression tests |
| F2 | **P0** `gradlew lintDebug` failed with 2 `MissingPermission` errors, so the CI Android job was red | Guarded call sites annotated; runtime permission check and `SecurityException` handling unchanged. `lintDebug` green |
| F3 | Every `audit_log.info` was discarded (logger at WARNING, no root handler) — §75 observability produced zero output | `configure_logging()` with `LOG_LEVEL`; request/provider/cache/fusion logs confirmed emitting live |
| F4 | The authority CAP feed (1 index + **9 documents**) was re-fetched on *every* weather/chat/alert request | Location-independent CAP documents cached 120 s (30 s negative) behind single-flight; per-location filtering unchanged. Warm bundle **3.0 s → 18 ms**. 3 tests |
| F5 | `scripts/check_accessibility.py` crashed with `StopIteration` (palettes had moved to `Theme.kt`) | Rewritten: parses both colour-scheme blocks, scans all 9 Kotlin files, adds the `errorContainer` pair, reports instead of crashing. 14 pairs pass, min 6.37:1 |
| F6 | Gemini had no retry (one transient 503 dropped every answer to the template) and only charged the budget on **success**, allowing unbounded retries during an outage | Retries once on 500/502/503/504 only — never on 429 quota — and charges every call. 2 tests |
| F7 | Single-flight futures left unretrieved exceptions, emitting asyncio warnings | Done-callback marks the exception retrieved; suite runs clean |
