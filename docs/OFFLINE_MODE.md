# Offline and low connectivity

Weather is downloaded in one compressed JSON bundle, saved atomically as a Room entity and observed by the UI. Chat messages are also stored in Room. No raw provider JSON is saved. Preferences are stored in DataStore. A six-hour WorkManager refresh defaults to unmetered networks with battery-not-low constraints; manual refresh is always available. Timing is controlled by Android and is not exact.

On a network failure, the UI retains downloaded weather and shows a saved-data notice. Local deterministic chat can summarize saved today/tomorrow weather and supports day follow-ups. If the required period is missing, it says so. The backend also retains stale cached forecasts and preserves their retrieval timestamps. No cache means no weather numbers.

A downloaded forecast is not a live observation. New warnings cannot arrive on a disconnected phone. Official warning ingestion is currently unimplemented even online, so warning availability is explicitly unknown. No notification subscription UI is exposed for an unsupported alert service.

Limitations: backend cache is in-process, not persistent; Android per-category alert/nowcast TTLs await those integrations; broader intent coverage remains pending. Real airplane-mode device tests have not yet run.

