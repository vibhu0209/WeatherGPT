# Implementation research record

The implementation uses official provider documentation and live probes where credentials permit. Open-Meteo GFS forecast, ECMWF IFS, marine, and ERA5 archive endpoints were exercised with real requests. OpenWeather and WeatherAPI parsers use recorded-schema fixtures because keys are optional. The published IMD API surface was probed, but normalized live forecasts remain blocked by required credentials. CAP handling follows CAP 1.2 and requires a trusted authority feed URL.

Android architecture follows Compose, Room, DataStore, and WorkManager contracts. Provider and model assumptions are encoded in tests and `DATA_SOURCES.md`. Research findings never upgrade an unavailable source into a successful integration.

