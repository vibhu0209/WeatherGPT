# Language support

The Android UI has complete string packs for all 11 requested language identifiers: `en`, `hi`, `bn`, `te`, `mr`, `ta`, `gu`, `kn`, `ml`, `pa`, `or` (**170/170** keys). Localization integrity (`scripts/check_localizations.py`) gates missing keys, placeholder mismatch, and leftover identical-to-English copy. Unused leftover onboarding/permission copy from an older 5-step flow was removed; every remaining key is referenced from Kotlin or layouts.

## Runtime path

Selected language is stored in DataStore, applied to the UI locale, and sent as `language` on `POST /v1/chat/message`.

1. Intent is resolved from the user text (including native-script rain/today/tomorrow chips).
2. Typed weather tools execute against canonical provider data.
3. A deterministic template in the selected language wraps verified numbers, units, timestamps, source names and official-alert fields.
4. When online and configured, Groq may orchestrate WeatherGPT tools and explain verified results. It cannot invent numbers, units, severity tokens or source names; failed validation falls back to the deterministic draft.
5. BHASHINI / Google Translate run only when credentials exist **and** the draft language still differs from the request. Failure keeps the deterministic draft.

Official CAP headline, instruction and severity stay verbatim (usually English from the feed). Wrappers are localized; the meaning is not rewritten.

## Honesty

- **Live translation is not complete** without BHASHINI or Google credentials. Adapters remain; `/v1/languages/capabilities` reports `live_translation: false` and `answer_mode: deterministic_templates`.
- Cloud STT/TTS (`POST /v1/voice/*`) returns **501**. On-device recognition and playback use `xx-IN` locale tags. Availability depends on the phone’s installed engines and is not claimed as complete.
- Native-speaker review of template quality remains required.

Offline chat uses the same selected language against the Room cache and never invents weather values.
