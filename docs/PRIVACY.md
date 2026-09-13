# WeatherGPT privacy

## Location privacy by design

| Rule | Implementation |
|---|---|
| Collect GPS only when needed | Optional one-shot last-known location; no continuous tracking |
| No background location | `ACCESS_BACKGROUND_LOCATION` is not requested |
| Prefer coarse location | Android requests `ACCESS_COARSE_LOCATION` only |
| Local source of truth | Saved places and chat stay in Room/DataStore on device |
| Android → backend only | Weather and AI calls go through WeatherGPT, never directly to provider APIs |
| Google Places key backend-only | Optional `GOOGLE_PLACES_API_KEY` lives in server `.env`; Android never receives it. Default `GOOGLE_PLACES_ENABLED=false` so local/SIH runs use free geocoders only. |
| Place search minimization | Typed search and GPS reverse geocode call Google only when enabled, keyed, and not in billing cooldown; otherwise Open-Meteo / Nominatim / local nearest city. |
| Minimal Groq / LLM context | Precise lat/lon stripped from conversation context and redacted from questions |
| No location in logs | Request audit logs omit query strings and coordinates; place logs use query length / provider only |
| No location in errors | Client errors are generic |
| Short server retention | Weather cache is grid-keyed and TTL-bound; no permanent location history |
| User deletion | Profile “Clear data” wipes Room, DataStore, WorkManager jobs and notifications |

## Data minimization

Stored by default:

- Current/saved place labels and coordinates (local)
- Cached weather bundles (local)
- Chat transcripts (local)
- Sync ETags / notification receipt hashes (local)

Not stored by default:

- Raw microphone audio
- GPS history trails
- Server-side chat history
- Hardware identifiers (IMEI/serial)

## Voice

Speech recognition uses the platform recognizer. Audio may leave the device through the OEM/Google engine. Typed chat remains available.

## Transparency

Official warnings and WeatherGPT risk estimates remain visually distinct. Stale/offline data is labelled. Clear-data is always available from Profile.
