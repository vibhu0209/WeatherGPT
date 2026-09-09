# WeatherGPT security

WeatherGPT is hardened for a SIH prototype. It is **not** claimed to be unhackable.

## Boundaries

```
Android (local Room / DataStore)
   ↓ HTTPS / validated server URL
WeatherGPT backend
   ↓ minimum necessary coordinates
Weather providers

Verified weather context
   ↓ redact precise GPS / secrets
Gemini / language services
```

## Controls implemented

| Area | Control |
|---|---|
| Secrets | Provider, Gemini, BHASHINI and Firebase credentials stay server-side only |
| API validation | Lat/lon bounds, chat length ≤1000, POST body ≤16 KiB, profile allowlist |
| Rate limiting | Per-IP sliding window (90/min) with bounded memory; no full-map wipe |
| Errors | Sanitized envelopes; no stack traces or coordinates in client errors |
| Logging | Audit logs record method/path/status/duration only — not query strings or chat text |
| Device isolation | Alert subscriptions require `X-Device-Id` + `Authorization: Bearer <device_token>` |
| SSRF | CAP and BHASHINI URLs must be HTTPS and host-allowlisted; CAP redirects disabled |
| Prompt injection | Deterministic draft + `validate_polish`; Gemini cannot invent numbers or warning severities |
| Gemini privacy | Coordinates redacted from questions; place labels only in drafts; call budget per minute |
| Headers | `nosniff`, `DENY` framing, `no-referrer`, restrictive Permissions-Policy |
| CORS | Off by default; enable via `CORS_ORIGINS` |
| Android | No weather API keys in APK; release cleartext disabled; backup disabled; coarse location only |

## Device tokens

`POST /v1/device/register` mints a random `device_id` and one-time `device_token`. The backend stores only a SHA-256 hash. Tokens can be revoked with `POST /v1/device/revoke`.

## Remaining risks

- Reverse proxies that log full URLs can still capture GET coordinates; prefer POST bundle/resolve and disable query logging.
- Room is not encrypted at rest; stolen unlocked devices can read local places/chat.
- Custom Android server URL is a trust boundary — users can point at a malicious host.
- In-memory subscription/device store is process-local; production needs PostgreSQL + Redis.
- No certificate pinning yet.
