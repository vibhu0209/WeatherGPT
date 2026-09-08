# Architecture and API

Android Compose UI → ViewModel → Repository → Retrofit backend / Room local database.
Weather UI observes Room Flow. Successful forecast downloads are validated and saved before display. Chat messages are persisted before display. DataStore holds language, theme, large text, selected place, profile and connection preferences. Raw voice audio is not stored by WeatherGPT.

Official alerts and WeatherGPT Risk Estimates are separate response collections and separate UI sections. Risk estimates are deterministic threshold results with their supporting value, unit, rationale, calculation time, and a non-official disclaimer. An empty local-risk list does not imply that no official warning exists.

Backend: FastAPI → typed location validation → asynchronous provider adapters → Pydantic normalized points → timestamp-aligned median consensus → deterministic answer templates.

Canonical units: Celsius, mm, metres/second, percentages, UTC timestamps with a separate IANA location timezone. Three-hour OpenWeather precipitation is deliberately excluded from one-hour fusion. Duplicate model families and stale provider retrievals are discarded. Missing values stay null.

Routes implemented:
- GET /health
- GET /v1/capabilities
- GET /v1/providers/status
- GET /v1/locations/search?q=...
- GET /v1/weather/bundle?latitude=...&longitude=...&name=...&timezone=...
- GET /v1/weather/current?latitude=...&longitude=...
- GET /v1/weather/hourly?latitude=...&longitude=...&hours=24
- GET /v1/weather/daily?latitude=...&longitude=...&days=7
- GET /v1/weather/score?latitude=...&longitude=...&profile=general
- GET /v1/weather/alerts?latitude=...&longitude=...
- GET /v1/climate/summary?latitude=...&longitude=...&metric=temperature&years=10
- POST /v1/chat/message (text, location, language, profile, day_offset)

See generated OpenAPI at /docs. No placeholder endpoint claims to perform unsupported functionality. All weather metadata includes retrieval time, sources, source count, consensus status, provider status and explicit alert unavailability.

Current follow-ups retain day offset in DataStore across restarts; full structured conversation sessions and arbitrary time ranges remain unimplemented. Selected location is explicit and persists. Arbitrary place extraction from chat is not implemented; use the place selector.

Backend cache is bounded in-process, with a 15-minute refresh interval, stale fallback and short provider failure suppression. A single failed provider does not fail all weather. JSON responses are compressed above 1 KB. Retries are limited to transport connection/timeouts. A reverse proxy request-body limit and distributed rate limiting are still needed before public deployment.
