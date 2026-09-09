"""Cache backend abstraction. Local development uses memory; production can swap in Redis."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any


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
    """Placeholder for a shared Redis cache. Not required for local SQLite development."""

    def __init__(self, redis_url: str):
        raise RuntimeError(
            "RedisCacheBackend requires an installed Redis client and REDIS_URL. "
            "Use MemoryCacheBackend for local development."
        )

    def get(self, key: str) -> Any | None:
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError
