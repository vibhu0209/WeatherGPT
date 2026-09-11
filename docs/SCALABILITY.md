# WeatherGPT scalability

## Target topology

```
Load balancer
   ↓
Stateless FastAPI workers
   ↓
Shared PostgreSQL + Redis cache + task queue
   ↓
Weather providers / Gemini / language APIs
```

Local development still runs with SQLite-compatible simplicity: in-memory `MemoryCacheBackend`, no Redis required.

## Weather request amplification

Problem: N users × 4 providers ≈ expensive upstream load.

Mitigations implemented:

1. **Geohash grid cache** (~5 km cells) so nearby users share forecast work
2. **Single-flight coalescing** so concurrent misses for the same grid share one upstream fetch
3. **Per-provider concurrency limits** (bulkheads)
4. **Circuit cooldown** after provider failures
5. **ETag / 304** for Android bundle refresh
6. **CacheBackend interface** ready for Redis

## Gemini cost control

- Deterministic draft is always produced first
- Gemini is optional wording polish only
- Per-process call budget (default 30/min)
- Coordinate redaction reduces accidental sensitive prompts
- On budget/transport/validation failure, the verified draft is returned

## Background work

Android WorkManager already runs the six-hour (or twelve-hour low-data) forecast refresh. A process-local Python task queue was removed because nothing enqueued jobs; production workers (Celery/RQ) remain a future swap, not a current feature.

## Horizontal readiness

| Component | Prototype | Production swap |
|---|---|---|
| Cache | `MemoryCacheBackend` | Redis via `REDIS_URL` |
| Devices/subscriptions | in-memory dict | PostgreSQL |
| Tasks | Android WorkManager for refresh; no in-process Python queue | Celery/RQ if the API must fan out |
| Rate limit | process-local | shared Redis limiter |

## Honest limits

A single Windows laptop prototype will not serve millions of users. The architecture avoids process-only weather state that would force a full rewrite when moving to multiple workers.
