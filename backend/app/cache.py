"""Cache backend abstraction. Local development uses memory; production can swap in Redis."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import Settings


class CacheBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class MemoryCacheBackend(CacheBackend):
    """Process-local FIFO cache with optional TTL. Suitable for SQLite/dev and single workers."""

    def __init__(self, max_entries: int = 256):
        self.max_entries = max_entries
        self._store: dict[str, tuple[datetime | None, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at and datetime.now(timezone.utc) >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        expires_at = None
        if ttl_seconds is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        if key not in self._store and len(self._store) >= self.max_entries:
            self._store.pop(next(iter(self._store)))
        self._store[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


class RedisCacheBackend(CacheBackend):
    """Shared Redis cache. Optional — MemoryCacheBackend remains the local default."""

    def __init__(self, redis_url: str):
        if not redis_url:
            raise ValueError('REDIS_URL is required for RedisCacheBackend')
        try:
            import redis
        except ImportError as error:
            raise RuntimeError('redis package is not installed. Use MemoryCacheBackend for local development.') from error
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._client.ping()

    def get(self, key: str) -> Any | None:
        raw = self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        payload = json.dumps(value, default=str)
        if ttl_seconds is None:
            self._client.set(key, payload)
        else:
            self._client.setex(key, int(ttl_seconds), payload)

    def delete(self, key: str) -> None:
        self._client.delete(key)


class RateLimitBackend(ABC):
    @abstractmethod
    def allow(self, key: str) -> bool: ...


class MemoryRateLimitBackend(RateLimitBackend):
    def __init__(self, limiter):
        self._limiter = limiter

    def allow(self, key: str) -> bool:
        return self._limiter.allow(key)


class RedisRateLimitBackend(RateLimitBackend):
    def __init__(self, redis_url: str, limit: int, window_seconds: float):
        if not redis_url:
            raise ValueError('REDIS_URL is required for RedisRateLimitBackend')
        try:
            import redis
        except ImportError as error:
            raise RuntimeError('redis package is not installed.') from error
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self.limit = limit
        self.window_seconds = int(window_seconds)

    def allow(self, key: str) -> bool:
        redis_key = f'rl:{key}'
        count = self._client.incr(redis_key)
        if count == 1:
            self._client.expire(redis_key, self.window_seconds)
        return count <= self.limit


def build_cache(max_entries: int = 256) -> CacheBackend:
    url = Settings().redis_url
    if url:
        try:
            return RedisCacheBackend(url)
        except Exception:
            pass
    return MemoryCacheBackend(max_entries=max_entries)
