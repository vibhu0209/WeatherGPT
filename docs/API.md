# API reference

FastAPI publishes the OpenAPI schema at `/openapi.json` and interactive documentation at `/docs`. Android uses place search, weather bundle, and chat routes; focused weather, alerts, score, marine, and climate routes support testing and future clients.

Weather responses carry retrieval time, sources, source count, agreement or confidence, and provider status. Missing values remain null. Validation failures include a structured error and request ID. Latitude and longitude are bounded, and chat text is limited to 1,000 characters.

Run `scripts/run_backend.ps1`, then inspect `http://localhost:8000/docs` for exact schemas. Debug emulators use `http://10.0.2.2:8000/`. Production Android builds require HTTPS.

Shared examples used by both test suites are in `contracts/weather_bundle.json`, `contracts/chat_answer.json`, and `contracts/error.json`. Android unit tests deserialize the bundle with the production Gson DTOs; backend tests validate canonical location/point fields and the error envelope.


## Conditional bundle refresh

GET /v1/weather/bundle accepts an hours value from 24 to 168 (default 168) and returns a private ETag and Cache-Control: private, max-age=300. Send the exact ETag in If-None-Match; an unchanged bundle returns 304 with an empty body. Clients must use 304 only when the matching local bundle exists.
