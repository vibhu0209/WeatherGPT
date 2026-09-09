# API reference

FastAPI publishes the OpenAPI schema at `/openapi.json` and interactive documentation at `/docs`. Android uses place search, weather bundle, chat, and related routes; focused weather, alerts, score, marine, climate, translate, and device/subscription routes support testing and future clients.

Weather responses carry retrieval time, sources, source count, agreement or confidence, and provider status. Missing values remain null. Validation failures include a structured error and request ID. Latitude and longitude are bounded, and chat text is limited to 1,000 characters.

Run `scripts/run_backend.ps1`, then inspect `http://localhost:8000/docs` for exact schemas. Debug emulators use `http://10.0.2.2:8000/`. Production Android builds require HTTPS.

Shared examples used by both test suites are in `contracts/weather_bundle.json`, `contracts/chat_answer.json`, and `contracts/error.json`. Android unit tests deserialize the bundle with the production Gson DTOs; backend tests validate canonical location/point fields and the error envelope.

Prefer **POST** bodies for coordinates on shared or logged networks. GET query forms remain for local debugging.

## Health and readiness

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness: `{ status, time }`. |
| GET | `/ready` | Readiness flags: `{ status: "ready", cache, gemini, cap_alerts, time }`. `gemini` is true only when key+model are configured; `cap_alerts` reflects whether `CAP_ALERT_URL` is set. Does not claim live IMD/FCM/SMS. |

## Locations

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/locations/search` | Open-Meteo geocoding; `q` min length 2. |
| GET | `/v1/locations/resolve` | Query `latitude`, `longitude`, optional `name`. Resolves IANA timezone via Open-Meteo. |
| POST | `/v1/locations/resolve` | JSON body: `{ latitude, longitude, name? }`. Same behaviour as GET; preferred for privacy. |

## Weather bundle and focused routes

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/weather/bundle` | Query lat/lon/name/timezone/`hours` (24–168, default 168). |
| POST | `/v1/weather/bundle` | JSON body: `{ latitude, longitude, name?, timezone?, hours? }`. Same payload as GET. |
| GET | `/v1/weather/current` | Current point from fused bundle. |
| GET | `/v1/weather/hourly` | Hourly slice. |
| GET | `/v1/weather/daily` | Daily summaries. |
| GET | `/v1/weather/score` | Profile weather score. |
| GET | `/v1/weather/alerts` | Official alerts (when CAP configured) + local risk estimates. |

### Conditional bundle refresh

GET and POST `/v1/weather/bundle` return a private ETag and `Cache-Control: private, max-age=300`. Send the exact ETag in `If-None-Match`; an unchanged bundle returns **304** with an empty body. Clients must use 304 only when the matching local bundle exists.

## Marine and climate

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/marine/forecast` | Open-Meteo Marine model sea state (not an official INCOIS/IMD warning). |
| GET | `/v1/weather/marine` | Alias of `/v1/marine/forecast`. |
| GET | `/v1/climate/summary` | ERA5-based temperature or rainfall trend summary. |

## Chat, translate, voice

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/chat/message` | Deterministic verified weather answer; optional Gemini wording when configured. |
| POST | `/v1/translate` | Body `{ text, source?, target }`. Uses BHASHINI then Google Translation when configured; otherwise returns original text with `fallback: true`. Does not invent weather numbers. |
| POST | `/v1/voice/transcribe` | **501** while cloud voice is disabled. Use on-device Android speech recognition. |
| POST | `/v1/voice/synthesize` | **501** while cloud voice is disabled. Use on-device Android TTS. |

`GET /v1/capabilities` reports `cloud_voice: false` and `demo_mode: false`.

## Device registration and alert subscriptions

Alert subscriptions are **device-owned**. Coordinates are never listed without a valid device token (IDOR hardening).

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/v1/device/register` | None | Optional body `{ device_id? }`. Returns `{ device_id, device_token, registered_at, … }`. Token is shown once; store privately. Backend stores a hash. |
| POST | `/v1/device/revoke` | Required | Revokes the device and its subscriptions. |
| POST | `/v1/alerts/subscriptions` | Required | Body `{ latitude, longitude, timezone?, channels? }`. Creates a subscription for the authenticated device. |
| GET | `/v1/alerts/subscriptions` | Required | Lists subscriptions for this device only. |
| DELETE | `/v1/alerts/subscriptions/{subscription_id}` | Required | Deletes only if owned by this device; otherwise 404. |

**Auth headers (required on revoke and subscription routes):**

- `X-Device-Id: <device_id>`
- `Authorization: Bearer <device_token>`

Missing or invalid auth returns **401**. Cross-device token use is rejected. Push/SMS delivery still requires configured `FIREBASE_*` / `SMS_*` credentials; without them transports report disabled.

## Other capability routes

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/capabilities` | Feature flags (forecast, chat mode, official_alerts, marine, climate, cloud_voice, gemini, demo_mode). |
| GET | `/v1/languages/capabilities` | UI languages and language-provider health. |
| GET | `/v1/providers/status` | Per-adapter health. |
